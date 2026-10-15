import hashlib, io, json, tempfile, unittest, uuid, wave, zipfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sonaweft_web.app import create_app
from sonaweft_web.config import Settings
from sonaweft_web.ledger import Ledger
from sonaweft_web.storage import Storage


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = Ledger(root / "db.sqlite")
        self.storage = Storage(root / "media")
        self.dispatches = []
        self.settings = Settings(Fernet.generate_key().decode(), hosted_ready=True)

        async def store(op, args):
            return getattr(self.db, op)(**args)

        async def storage(op, args):
            return self.storage.execute(op, args)

        async def dispatch(job):
            self.dispatches.append(job)

        self.app = create_app(self.settings, store, storage, dispatch)
        self.c = TestClient(self.app, base_url="https://testserver")
        self.csrf = self.c.get("/api/session").json()["csrf"]

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def post(self, path, body):
        return self.c.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def media(self):
        f = io.BytesIO()
        with wave.open(f, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\0" * 32000)
        return f.getvalue()

    def upload(self, data=None):
        return self.c.post(
            "/api/uploads",
            files={
                "file": (
                    "recording.wav",
                    data if data is not None else self.media(),
                    "audio/wav",
                )
            },
            data={"request_id": str(uuid.uuid4())},
            headers={"X-CSRF-Token": self.csrf},
        )

    def trial(self):
        u = self.upload()
        self.assertEqual(u.status_code, 200)
        r = self.post(
            "/api/jobs",
            {
                "upload": u.json()["upload"],
                "request_id": str(uuid.uuid4()),
                "trial": True,
                "expected_units": 0,
                "authorized_media": True,
            },
        )
        self.assertEqual(r.status_code, 200)
        return r.json()

    def finish(self, j):
        self.db.start(j["id"])
        self.db.finish(j["id"], True)
        raw = {
            "model": "synthetic",
            "duration": 1.0,
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "id": 0,
                    "text": "Original words.",
                    "words": [],
                }
            ],
        }
        root = self.storage.directory(j["upload"])
        (root / ("result-" + j["id"] + ".json")).write_text(
            json.dumps(
                {
                    "transcript": raw,
                    "review": None,
                    "source": {"title": "Recording", "kind": "fixture"},
                }
            )
        )
        return raw

    def test_scholarly_lookup_requires_consent_owned_claim_and_rate_limit(self):
        j = self.trial()
        self.finish(j)
        path = self.storage.directory(j["upload"]) / ("result-" + j["id"] + ".json")
        result = json.loads(path.read_text())
        result["review"] = {
            "summary_md": "A summary.",
            "corrections": [],
            "claims": [
                {
                    "segment_id": "s000000",
                    "quote": "Original words.",
                    "question": "Which source supports this?",
                }
            ],
        }
        path.write_text(json.dumps(result))
        route = "/api/jobs/" + j["id"] + "/sources"
        with patch(
            "sonaweft_web.research.candidates", new_callable=AsyncMock
        ) as lookup:
            lookup.return_value = {"sources": [], "notice": "Not a verdict."}
            self.assertEqual(self.post(route, {"claim_index": 0}).status_code, 400)
            self.assertEqual(
                self.post(
                    route, {"claim_index": 1, "research_consent": True}
                ).status_code,
                400,
            )
            lookup.assert_not_called()
            for _ in range(5):
                self.assertEqual(
                    self.post(
                        route, {"claim_index": 0, "research_consent": True}
                    ).status_code,
                    200,
                )
            self.assertEqual(
                self.post(
                    route, {"claim_index": 0, "research_consent": True}
                ).status_code,
                429,
            )
            self.assertEqual(lookup.await_count, 5)
        with TestClient(self.app, base_url="https://testserver") as other:
            csrf = other.get("/api/session").json()["csrf"]
            self.assertEqual(
                other.post(
                    route,
                    json={"claim_index": 0, "research_consent": True},
                    headers={"X-CSRF-Token": csrf},
                ).status_code,
                404,
            )

    def test_real_media_inspection_quote_and_paid_boundary(self):
        r = self.upload()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["quotes"]["none"]["units"], 1650)
        self.assertEqual(self.dispatches, [])
        denied = self.post(
            "/api/jobs",
            {
                "upload": r.json()["upload"],
                "request_id": str(uuid.uuid4()),
                "trial": False,
                "expected_units": 1650,
                "authorized_media": True,
            },
        )
        self.assertEqual(denied.status_code, 402)
        self.assertEqual(self.dispatches, [])

    def test_trial_requires_rights_no_llm_and_idempotency(self):
        upload = self.upload().json()
        body = {
            "upload": upload["upload"],
            "request_id": str(uuid.uuid4()),
            "trial": True,
            "expected_units": 0,
        }
        self.assertEqual(self.post("/api/jobs", body).status_code, 400)
        body["authorized_media"] = True
        a = self.post("/api/jobs", body)
        b = self.post("/api/jobs", body)
        self.assertEqual(a.json()["id"], b.json()["id"])
        self.assertEqual(len(self.dispatches), 1)
        body["review"] = "standard"
        self.assertEqual(self.post("/api/jobs", body).status_code, 400)

    def test_corrections_export_and_cross_workspace_isolation(self):
        j = self.trial()
        raw = self.finish(j)
        self.assertEqual(
            self.c.get("/api/jobs/" + j["id"]).json()["segments"][0]["text"],
            "Original words.",
        )
        path = "/api/jobs/" + j["id"] + "/edit"
        r = self.post(
            path, {"revision": 0, "corrections": {"s000000": "Corrected words."}}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.post(path, {"revision": 0, "corrections": {}}).status_code, 409
        )
        self.assertEqual(
            self.post(
                path, {"revision": 1, "corrections": {"unknown": "Wrong"}}
            ).status_code,
            400,
        )
        r = self.c.get("/api/jobs/" + j["id"] + "/export")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(json.loads(z.read("transcript.json")), raw)
            self.assertIn(b"Corrected words.", z.read("corrected.md"))
            manifest = json.loads(z.read("manifest.json"))
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
        with TestClient(self.app, base_url="https://testserver") as other:
            other.get("/api/session")
            for ending in ("", "/audio", "/export"):
                self.assertEqual(
                    other.get("/api/jobs/" + j["id"] + ending).status_code, 404
                )

    def test_recovery_restores_only_with_private_key(self):
        j = self.trial()
        key = self.post("/api/recovery", {}).json()["recovery_key"]
        with TestClient(self.app, base_url="https://testserver") as other:
            csrf = other.get("/api/session").json()["csrf"]
            r = other.post(
                "/api/restore",
                json={"recovery_key": key},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(other.get("/api/jobs/" + j["id"]).status_code, 200)

    def test_corrupt_media_ssrf_playlist_and_csrf_are_rejected(self):
        self.assertEqual(self.upload(b"not media").status_code, 409)
        self.assertEqual(
            self.upload(
                b"#EXTM3U\nhttp://169.254.169.254/latest/meta-data/\n"
            ).status_code,
            409,
        )
        self.assertEqual(self.c.post("/api/jobs", json={}).status_code, 403)
        self.assertEqual(
            self.c.post(
                "/api/recovery",
                json={},
                headers={
                    "X-CSRF-Token": self.csrf,
                    "Origin": "https://untrusted.invalid",
                },
            ).status_code,
            403,
        )

    def test_policy_responsiveness_boundary_and_closed_checkout_configuration(self):
        for path in ("/", "/pricing", "/terms", "/privacy", "/refunds", "/checkout"):
            self.assertEqual(self.c.get(path).status_code, 200)
        self.assertFalse(self.c.get("/api/checkout-config").json()["enabled"])
        self.assertNotIn(
            "cdn.paddle.com", self.c.get("/").headers["Content-Security-Policy"]
        )
        self.assertIn(
            "cdn.paddle.com", self.c.get("/checkout").headers["Content-Security-Policy"]
        )
        self.assertEqual(
            self.post("/api/checkout", {"pack": 5, "terms_accepted": True}).status_code,
            402,
        )
