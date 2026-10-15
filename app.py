"""Sonaweft: independent scale-to-zero deployment, secrets and durable ledger."""

import asyncio, json, shutil, time
from pathlib import Path
import modal

app = modal.App("sonaweft")
data_volume = modal.Volume.from_name("sonaweft-media-v1", create_if_missing=True)
ledger_volume = modal.Volume.from_name("sonaweft-ledger-v1", create_if_missing=True)
model_volume = modal.Volume.from_name("sonaweft-models-v1", create_if_missing=True)
base = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi==0.141.1",
        "httpx==0.28.1",
        "cryptography==46.0.5",
        "python-multipart==0.0.32",
        "requests==2.32.5",
    )
    .add_local_dir("instascript", "/root/instascript")
    .add_local_dir("sonaweft_web", "/root/sonaweft_web")
)
gpu_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04", add_python="3.12"
    )
    .apt_install("libgomp1")
    .pip_install(
        "faster-whisper==1.2.1",
        "av==15.1.0",
        "huggingface-hub==2.2.0",
        "ctranslate2==4.8.3",
        "protobuf==6.33.6",
    )
    .add_local_dir("instascript", "/root/instascript")
    .add_local_dir("sonaweft_web", "/root/sonaweft_web")
)

OPERATIONS = {
    "account",
    "set_recovery",
    "recover",
    "credit",
    "purchase_list",
    "payment_intent",
    "payment_lookup",
    "payment_receipt",
    "payment_event",
    "payment_pending",
    "payment_done",
    "upload",
    "upload_get",
    "confirm",
    "start",
    "stage",
    "finish",
    "get",
    "internal",
    "list",
    "cancel",
    "edit",
    "event",
    "admit_request",
    "cleanup",
    "stale",
    "control",
    "operations",
    "snapshot",
}


@app.function(
    image=base,
    volumes={"/ledger": ledger_volume},
    max_containers=1,
    timeout=60,
    cpu=(0.125, 0.5),
    memory=512,
    scaledown_window=5,
)
def store(operation, arguments):
    from sonaweft_web.ledger import Ledger

    if operation not in OPERATIONS:
        raise ValueError("Unknown operation")
    ledger_volume.reload()
    value = getattr(Ledger("/ledger/state.sqlite"), operation)(**arguments)
    ledger_volume.commit()
    return value


@app.function(
    image=gpu_image,
    gpu="L4",
    volumes={"/models": model_volume, "/data": data_volume},
    max_containers=1,
    timeout=600,
    scaledown_window=5,
)
def speech(upload, seconds):
    try:
        from huggingface_hub import snapshot_download
        from faster_whisper import WhisperModel
        import uuid

        model_volume.reload()
        data_volume.reload()
        path = snapshot_download(
            "Systran/faster-whisper-large-v3",
            revision="edaa852ec7e145841d8ffdb056a99866b5f0a478",
            cache_dir="/models",
            allow_patterns=["*.json", "*.txt", "*.bin"],
        )
        model_volume.commit()
        model = WhisperModel(path, device="cuda", compute_type="int8_float16")
        from sonaweft_web.storage import audio_name

        audio = Path("/data") / str(uuid.UUID(upload)) / audio_name(seconds)
        values, info = model.transcribe(
            str(audio),
            language="en",
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=5,
        )
        rows = []
        for s in values:
            rows.append(
                {
                    "id": int(s.id),
                    "start": round(float(s.start), 3),
                    "end": round(float(s.end), 3),
                    "text": s.text.strip(),
                    "words": [
                        {
                            "word": w.word,
                            "start": round(float(w.start), 3),
                            "end": round(float(w.end), 3),
                            "probability": round(float(w.probability), 4),
                        }
                        for w in (s.words or [])
                    ],
                    "avg_logprob": float(s.avg_logprob),
                    "no_speech_prob": float(s.no_speech_prob),
                }
            )
        if not rows:
            raise ValueError(
                "No speech was detected; no processing credit was consumed."
            )
        return {
            "model": "Systran/faster-whisper-large-v3",
            "model_revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            "language": "en",
            "duration": round(min(float(info.duration), float(seconds)), 3),
            "audio_file": audio.name,
            "segments": rows,
        }
    except Exception as error:
        import re

        return {
            "_error": {
                "type": type(error).__name__,
                "message": re.sub(r"https?://\S+", "[provider URL]", str(error))[:400],
            }
        }


@app.function(
    image=base,
    secrets=[modal.Secret.from_name("sonaweft-llm")],
    max_containers=1,
    timeout=180,
    cpu=(0.125, 0.5),
    memory=512,
    scaledown_window=5,
)
def review(transcript, mode):
    from instascript.review import review_transcript

    return review_transcript(transcript, mode)


@app.function(
    image=base,
    volumes={"/data": data_volume},
    max_containers=1,
    timeout=1200,
    cpu=(0.5, 1),
    memory=2048,
    scaledown_window=5,
)
def process(job):
    from sonaweft_web.media import normalize
    from sonaweft_web.storage import Storage, audio_name
    from instascript.contract import validate_transcript, validate_review
    from instascript.pipeline import atomic_json

    if not store.remote("start", {"job": job}):
        return
    j = store.remote("internal", {"job": job})
    data_volume.reload()
    root = Storage("/data").directory(j["upload"])
    normal = root / audio_name(j["seconds"])
    raw_path = normal.with_suffix(".json")
    try:
        if not normal.exists():
            normalize(root / "source.media", normal, j["seconds"])
            data_volume.commit()
        store.remote("stage", {"job": job, "stage": "transcribing"})
        if raw_path.exists():
            raw = validate_transcript(json.loads(raw_path.read_text()))
        else:
            raw = speech.remote(j["upload"], j["seconds"])
            if "_error" in raw:
                print("sonaweft asr_diagnostic", raw["_error"])
                raise RuntimeError("ASR worker needs attention.")
            validate_transcript(raw)
            atomic_json(raw_path, raw)
            data_volume.commit()
        checked = None
        if j["review"] != "none":
            store.remote("stage", {"job": job, "stage": "reviewing"})
            checked = review.remote(raw, j["review"])
            validate_review(raw, checked)
        store.remote("stage", {"job": job, "stage": "exporting"})
        upload = store.remote(
            "upload_get", {"owner": j["owner"], "upload": j["upload"]}
        )
        result = {
            "transcript": raw,
            "review": checked,
            "source": {
                "title": upload["filename"],
                "kind": "uploaded-media",
                "source_sha256": __import__("hashlib")
                .sha256((root / "source.media").read_bytes())
                .hexdigest(),
                "review_model": {
                    "standard": "deepseek-flash",
                    "advanced": "deepseek-v4-pro",
                }.get(j["review"]),
            },
        }
        atomic_json(root / ("result-" + job + ".json"), result)
        data_volume.commit()
        store.remote("finish", {"job": job, "success": True})
    except Exception as error:
        # No transcript/provider error payloads in cloud logs or public messages.
        store.remote(
            "finish",
            {
                "job": job,
                "success": False,
                "error": "Processing failed; reserved credit was returned. Retained ASR checkpoints can be reused on explicit retry.",
            },
        )
        store.remote("event", {"kind": "job_error"})
        print(
            "sonaweft job_failed",
            {
                "stage": store.remote("internal", {"job": job})["stage"],
                "exception": type(error).__name__,
            },
        )


async def store_async(op, args):
    return await store.remote.aio(op, args)


@app.function(
    image=base,
    secrets=[
        modal.Secret.from_name("sonaweft-session"),
        modal.Secret.from_name("sonaweft-payments"),
    ],
    max_containers=1,
    timeout=300,
    cpu=(0.125, 0.5),
    memory=512,
    scaledown_window=5,
)
def payment_events():
    from sonaweft_web.config import Settings
    from sonaweft_web.paddle import PaddleCreditProvider
    from sonaweft_web.payments import process_paddle_events

    s = Settings.from_env()
    if s.billing_ready:
        return asyncio.run(process_paddle_events(PaddleCreditProvider(s), store_async))


@app.function(
    image=base,
    volumes={"/data": data_volume},
    secrets=[
        modal.Secret.from_name("sonaweft-session"),
        modal.Secret.from_name("sonaweft-payments"),
    ],
    max_containers=1,
    timeout=180,
    cpu=(0.25, 1),
    memory=2048,
    scaledown_window=5,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def web_app():
    from threading import Lock
    from sonaweft_web.config import Settings
    from sonaweft_web.app import create_app
    from sonaweft_web.storage import Storage

    lock = Lock()

    async def storage(op, args):
        def execute():
            with lock:
                data_volume.reload()
                value = Storage("/data").execute(op, args)
                if op == "put":
                    data_volume.commit()
                return value

        return await asyncio.to_thread(execute)

    async def dispatch(job):
        return (await process.spawn.aio(job)).object_id

    async def payments():
        return (await payment_events.spawn.aio()).object_id

    return create_app(Settings.from_env(), store_async, storage, dispatch, payments)


@app.function(
    image=base,
    volumes={"/data": data_volume},
    secrets=[
        modal.Secret.from_name("sonaweft-session"),
        modal.Secret.from_name("sonaweft-payments"),
    ],
    schedule=modal.Period(hours=1),
    max_containers=1,
    timeout=300,
    cpu=(0.125, 0.5),
    memory=512,
    scaledown_window=5,
)
def cleanup():
    from cryptography.fernet import Fernet
    from sonaweft_web.config import Settings
    from sonaweft_web.paddle import PaddleCreditProvider
    from sonaweft_web.payments import process_paddle_events, reconcile_paddle

    expired = store.remote("cleanup", {})
    data_volume.reload()
    for uid in expired:
        shutil.rmtree(Path("/data") / uid, ignore_errors=True)
    s = Settings.from_env()
    if s.billing_ready:

        async def run():
            p = PaddleCreditProvider(s)
            await process_paddle_events(p, store_async)
            rows = await store_async("purchase_list", {})
            for row in sorted(
                (
                    r
                    for r in rows
                    if r["verified"]
                    and r["order_id"].startswith(p.prefix)
                    and r["revoked"] < r["granted"]
                ),
                key=lambda r: r["checked"],
            )[:50]:
                try:
                    await reconcile_paddle(
                        p, store_async, row["order_id"].rsplit(":", 1)[-1]
                    )
                except Exception:
                    await store_async("event", {"kind": "reconcile_error"})

        asyncio.run(run())
    backups = Path("/data/financial-backups")
    backups.mkdir(exist_ok=True)
    today = backups / (time.strftime("%Y-%m-%d", time.gmtime()) + ".fernet")
    if not today.exists():
        today.write_bytes(
            Fernet(s.session_key.encode()).encrypt(store.remote("snapshot", {}))
        )
    for old in sorted(backups.glob("*.fernet"))[:-7]:
        old.unlink()
    data_volume.commit()
    print("sonaweft cleanup", store.remote("operations", {}))
