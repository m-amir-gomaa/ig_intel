"""Sonaweft web boundary: ownership, explicit processing consent and cost admission."""

import asyncio, hashlib, hmac, io, json, secrets, tempfile, uuid, zipfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from instascript.contract import bundle, segments
from . import media
from .config import quote
from .errors import DomainError, BillingError
from .paddle import PaddleCreditProvider, valid_id
from .payments import reconcile_paddle, process_paddle_events

ROOT = Path(__file__).parent


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        limit = (
            self.limit + 65536 if scope.get("path") == "/api/uploads" else 256 * 1024
        )
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length < 0 or length > limit:
            return await JSONResponse(
                {"detail": "Request exceeds the size limit."}, 413
            )(scope, receive, send)
        total = 0

        async def bounded():
            nonlocal total
            event = await receive()
            total += len(event.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Request exceeds the size limit.")
            return event

        return await self.app(scope, bounded, send)


def create_app(
    settings, store, storage, dispatch, payment_dispatcher=None, provider=None
):
    app = FastAPI(title="Sonaweft", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit, limit=settings.max_bytes)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    cipher = Fernet(settings.session_key.encode())
    provider = provider or PaddleCreditProvider(settings)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"detail": str(error)}, 409)

    @app.exception_handler(json.JSONDecodeError)
    async def invalid_json(request, error):
        return JSONResponse({"detail": "Invalid request. Refresh and retry."}, 400)

    def identity(value):
        return hmac.new(
            settings.session_key.encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    def session(request):
        try:
            value = json.loads(
                cipher.decrypt(
                    request.cookies.get("sonaweft_session", "").encode(), ttl=30 * 86400
                )
            )
            if str(uuid.UUID(value["uid"])) != value["uid"] or not isinstance(
                value["csrf"], str
            ):
                raise ValueError()
            return value
        except (ValueError, KeyError, TypeError, InvalidToken):
            raise HTTPException(
                401, "Refresh to create a secure workspace session."
            ) from None

    def cookie(response, value):
        response.set_cookie(
            "sonaweft_session",
            cipher.encrypt(json.dumps(value).encode()).decode(),
            secure=True,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
            path="/",
        )

    def csrf(request, value):
        if request.headers.get("origin", str(request.base_url).rstrip("/")) != str(
            request.base_url
        ).rstrip("/") or not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), value["csrf"]
        ):
            raise HTTPException(403, "Refresh the page before trying again.")

    def ident(request):
        return identity(
            "rate:"
            + (
                (request.headers.get("x-forwarded-for", "").split(",")[-1].strip())
                or (request.client.host if request.client else "unknown")
            )
        )

    async def throttle(request, bucket):
        try:
            await store("admit_request", {"bucket": bucket, "identity": ident(request)})
        except DomainError:
            raise HTTPException(
                429,
                "Too many requests. Retry in one minute.",
                headers={"Retry-After": "60"},
            ) from None

    async def payload(request):
        value = await request.json()
        if not isinstance(value, dict):
            raise HTTPException(400, "Expected a JSON object.")
        return value

    def uid(value):
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(400, "Invalid identifier.") from None

    def live():
        if not settings.billing_ready:
            raise HTTPException(
                402,
                "Paid packs open after merchant approval and payment verification. The sample and local CLI remain separate.",
            )

    async def owned(request, job):
        result = await store("get", {"owner": session(request)["uid"], "job": uid(job)})
        if not result:
            raise HTTPException(404, "Result not found or expired.")
        return result

    def public(job):
        return {
            k: job[k]
            for k in (
                "id",
                "upload",
                "review",
                "trial",
                "seconds",
                "units",
                "status",
                "stage",
                "expires",
                "error",
                "revision",
            )
            if k in job
        }

    @app.middleware("http")
    async def secure_headers(request, next):
        result = await next(request)
        csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self' https://m-amir-gomaa.github.io; base-uri 'none'; form-action 'self'; object-src 'none'"
        if request.url.path == "/checkout":
            csp = "default-src 'self'; script-src 'self' https://cdn.paddle.com; style-src 'self'; connect-src 'self' https://*.paddle.com; frame-src https://*.paddle.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
        result.headers.update(
            {
                "Content-Security-Policy": csp,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return result

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "templates/index.html", media_type="text/html")

    @app.get("/checkout")
    @app.get("/pricing")
    @app.get("/terms")
    @app.get("/privacy")
    @app.get("/refunds")
    async def page(request: Request):
        return FileResponse(
            ROOT / "templates" / (request.url.path[1:] + ".html"),
            media_type="text/html",
        )

    @app.get("/health")
    async def health():
        return {
            "service": "sonaweft",
            "status": "ok",
            "hosted_enabled": settings.hosted_ready,
            "billing_enabled": settings.billing_ready,
            "billing_provider": "paddle",
        }

    @app.get("/api/session")
    async def start(request: Request):
        await throttle(request, "session")
        try:
            value = session(request)
        except HTTPException:
            value = {"uid": str(uuid.uuid4()), "csrf": secrets.token_urlsafe(32)}
        account = await store("account", {"owner": value["uid"]})
        result = JSONResponse(
            {
                "csrf": value["csrf"],
                "account": account,
                "billing_enabled": settings.billing_ready,
                "hosted_enabled": settings.hosted_ready,
                "max_bytes": settings.max_bytes,
                "max_seconds": settings.max_seconds,
                "trial_seconds": settings.trial_seconds,
            }
        )
        cookie(result, value)
        return result

    @app.post("/api/recovery")
    async def recovery(request: Request):
        value = session(request)
        csrf(request, value)
        key = secrets.token_urlsafe(40)
        await store(
            "set_recovery", {"owner": value["uid"], "key": identity("recover:" + key)}
        )
        return {
            "recovery_key": key,
            "notice": "Save privately. Creating a new key invalidates the old key.",
        }

    @app.post("/api/restore")
    async def restore(request: Request):
        value = session(request)
        csrf(request, value)
        body = await payload(request)
        key = body.get("recovery_key", "")
        if not isinstance(key, str) or not 30 <= len(key) <= 100:
            raise HTTPException(400, "Enter your private recovery key.")
        owner = await store("recover", {"key": identity("recover:" + key)})
        if not owner:
            raise HTTPException(401, "Recovery key not found.")
        result = JSONResponse({"restored": True})
        cookie(result, {"uid": owner, "csrf": secrets.token_urlsafe(32)})
        return result

    @app.post("/api/logout")
    async def logout(request: Request):
        value = session(request)
        csrf(request, value)
        response = JSONResponse({"signed_out": True})
        response.delete_cookie("sonaweft_session", path="/")
        return response

    @app.post("/api/uploads")
    async def upload(
        request: Request, file: UploadFile = File(...), request_id: str = Form(...)
    ):
        value = session(request)
        csrf(request, value)
        await throttle(request, "upload")
        rid = uid(request_id)
        if not settings.hosted_ready:
            raise HTTPException(
                503,
                "Hosted processing is being verified. Use the public example or local CLI.",
            )
        data = await file.read(settings.max_bytes + 1)
        if not data or len(data) > settings.max_bytes:
            raise HTTPException(413, "Choose media within the displayed size limit.")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "upload.media"
            path.write_bytes(data)
            duration = await asyncio.to_thread(media.inspect, path)
        item = await store(
            "upload",
            {
                "owner": value["uid"],
                "request": rid,
                "filename": Path(file.filename or "recording").name,
                "duration": duration,
                "size": len(data),
                "retention": settings.retention_seconds,
            },
        )
        await storage("put", {"upload": item["id"], "data": data})
        await store("event", {"kind": "upload"})
        return {
            "upload": item["id"],
            "filename": item["filename"],
            "duration": duration,
            "expires": item["expires"],
            "quotes": {
                mode: quote(duration, mode) for mode in ("none", "standard", "advanced")
            },
        }

    @app.post("/api/jobs")
    async def confirm(request: Request):
        value = session(request)
        csrf(request, value)
        await throttle(request, "job")
        body = await payload(request)
        if not settings.hosted_ready:
            raise HTTPException(503, "Hosted processing is paused for verification.")
        trial = body.get("trial", False)
        if type(trial) is not bool:
            raise HTTPException(400, "Invalid trial selection.")
        if not trial:
            live()
        if body.get("authorized_media") is not True:
            raise HTTPException(400, "Confirm that you may process this media.")
        review = body.get("review", "none")
        if review != "none" and body.get("ai_consent") is not True:
            raise HTTPException(
                400,
                "Optional AI review sends transcript text to DeepSeek. Confirm before starting.",
            )
        job = await store(
            "confirm",
            {
                "owner": value["uid"],
                "upload": uid(body.get("upload")),
                "request": uid(body.get("request_id")),
                "review": review,
                "trial": trial,
                "identity": ident(request),
                "expected": body.get("expected_units"),
            },
        )
        uncertain = False
        if job["new"]:
            try:
                await dispatch(job["id"])
            except Exception:
                uncertain = True
        return {**public(job), "submission_uncertain": uncertain}

    @app.get("/api/jobs")
    async def jobs(request: Request):
        value = session(request)
        await throttle(request, "read")
        await store("stale", {})
        return [
            {**public(j), "filename": j["filename"]}
            for j in await store("list", {"owner": value["uid"]})
        ]

    @app.get("/api/jobs/{job}")
    async def job(request: Request, job: str):
        await throttle(request, "read")
        j = await owned(request, job)
        result = public(j)
        if j["status"] == "done":
            content = await storage("result", {"upload": j["upload"], "job": j["id"]})
            result.update(
                {
                    "segments": segments(content["transcript"]),
                    "review_data": content.get("review"),
                    "corrections": json.loads(j["corrections"]),
                }
            )
        return result

    @app.post("/api/jobs/{job}/sources")
    async def sources(request: Request, job: str):
        value = session(request)
        csrf(request, value)
        j = await owned(request, job)
        body = await payload(request)
        if body.get("research_consent") is not True:
            raise HTTPException(
                400, "Confirm whether this claim may be sent to Crossref."
            )
        if j["status"] != "done":
            raise HTTPException(409, "Wait for the complete result.")
        content = await storage("result", {"upload": j["upload"], "job": j["id"]})
        claims = (content.get("review") or {}).get("claims", [])
        index = body.get("claim_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(claims)
        ):
            raise HTTPException(400, "Choose an existing source-linked claim.")
        await throttle(request, "research")
        from .research import candidates

        return await candidates(claims[index]["quote"])

    @app.post("/api/jobs/{job}/cancel")
    async def cancel(request: Request, job: str):
        value = session(request)
        csrf(request, value)
        await store("cancel", {"owner": value["uid"], "job": uid(job)})
        return {"cancelled": True}

    @app.post("/api/jobs/{job}/edit")
    async def edit(request: Request, job: str):
        value = session(request)
        csrf(request, value)
        j = await owned(request, job)
        body = await payload(request)
        if j["status"] != "done":
            raise HTTPException(409, "Wait for the complete result before editing.")
        content = await storage("result", {"upload": j["upload"], "job": j["id"]})
        try:
            bundle(
                content["transcript"], content["source"], None, body.get("corrections")
            )
        except (ValueError, TypeError):
            raise HTTPException(
                400, "Corrections must refer to existing transcript segments."
            ) from None
        revision = await store(
            "edit",
            {
                "owner": value["uid"],
                "job": j["id"],
                "revision": body.get("revision"),
                "corrections": body.get("corrections"),
            },
        )
        return {"revision": revision}

    @app.get("/api/jobs/{job}/export")
    async def export(request: Request, job: str, format: str = "bundle"):
        await throttle(request, "read")
        j = await owned(request, job)
        if j["status"] != "done":
            raise HTTPException(409, "The complete result is not ready.")
        content = await storage("result", {"upload": j["upload"], "job": j["id"]})
        files = bundle(
            content["transcript"],
            content["source"],
            content.get("review"),
            json.loads(j["corrections"]),
        )
        types = {
            "md": ("transcript.md", "text/markdown"),
            "srt": ("transcript.srt", "application/x-subrip"),
            "vtt": ("transcript.vtt", "text/vtt"),
            "json": ("transcript.json", "application/json"),
        }
        await store("event", {"kind": "download"})
        if format in types:
            filename, mime = types[format]
            return Response(
                files[filename],
                media_type=mime,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        if format != "bundle":
            raise HTTPException(400, "Choose bundle, md, json, srt or vtt.")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, text in files.items():
                archive.writestr(name, text)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="sonaweft-export.zip"'
            },
        )

    @app.get("/api/jobs/{job}/audio")
    async def audio(request: Request, job: str):
        j = await owned(request, job)
        if j["status"] != "done":
            raise HTTPException(409, "Audio review opens with the complete result.")
        result = await storage(
            "audio",
            {
                "upload": j["upload"],
                "seconds": j["seconds"],
                "range": request.headers.get("range"),
            },
        )
        return Response(
            result["data"],
            status_code=result["status"],
            media_type="audio/wav",
            headers=result["headers"],
        )

    @app.post("/api/jobs/{job}/sources")
    async def sources(request: Request, job: str):
        value = session(request)
        csrf(request, value)
        await throttle(request, "research")
        j = await owned(request, job)
        body = await payload(request)
        if j["status"] != "done" or body.get("research_consent") is not True:
            raise HTTPException(
                400, "Confirm sending this claim text to Crossref for metadata lookup."
            )
        content = await storage("result", {"upload": j["upload"], "job": j["id"]})
        index = body.get("claim_index")
        claims = (content.get("review") or {}).get("claims", [])
        if type(index) is not int or not 0 <= index < len(claims):
            raise HTTPException(400, "Select a claim from this result.")
        from .research import candidates

        return await candidates(claims[index]["quote"])

    @app.get("/api/checkout-config")
    async def checkout_config():
        return {
            "enabled": settings.billing_ready,
            "client_token": settings.paddle_client_token
            if settings.billing_ready
            else "",
            "environment": settings.paddle_environment,
        }

    @app.post("/api/checkout")
    async def checkout(request: Request):
        value = session(request)
        csrf(request, value)
        live()
        await throttle(request, "payment")
        body = await payload(request)
        if body.get("terms_accepted") is not True:
            raise HTTPException(
                400, "Accept the terms and refund/privacy notices before checkout."
            )
        if not (await store("account", {"owner": value["uid"]}))["has_recovery"]:
            raise HTTPException(409, "Create and save your recovery key first.")
        try:
            result = await provider.checkout(value["uid"], body.get("pack"))
        except BillingError as e:
            raise HTTPException(503, str(e)) from None
        await store(
            "payment_intent",
            {
                "transaction_id": result["transaction_id"],
                "owner": value["uid"],
                "units": result["units"],
            },
        )
        return {"url": result["url"]}

    @app.post("/api/payment-status")
    async def payment_status(request: Request):
        value = session(request)
        csrf(request, value)
        live()
        await throttle(request, "payment")
        body = await payload(request)
        txn = body.get("transaction_id")
        if not valid_id(txn, "txn"):
            raise HTTPException(400, "Invalid transaction.")
        intent = await store("payment_lookup", {"transaction_id": txn})
        if not intent or intent["owner"] != value["uid"]:
            raise HTTPException(
                404, "Checkout not found. Restore your workspace first."
            )
        try:
            return {"status": await reconcile_paddle(provider, store, txn)}
        except BillingError as e:
            raise HTTPException(503, str(e)) from None

    @app.post("/api/payment-event")
    async def payment_event(request: Request):
        live()
        raw = await request.body()
        if len(raw) > 65536:
            raise HTTPException(413, "Event too large.")
        try:
            event = provider.webhook(raw, request.headers.get("paddle-signature", ""))
        except BillingError as e:
            raise HTTPException(400, str(e)) from None
        if not event or not await store(
            "payment_lookup", {"transaction_id": event["transaction_id"]}
        ):
            return {"received": True, "ignored": True}
        if await store("payment_event", event):
            if payment_dispatcher:
                try:
                    await payment_dispatcher()
                except Exception:
                    await store("event", {"kind": "reconcile_error"})
            else:
                await process_paddle_events(provider, store)
        return {"received": True}

    return app
