from fastapi.testclient import TestClient
from sonaweft_web.app import create_app

"""Paddle boundaries use synthetic HTTP responses and real disposable SQLite."""

import asyncio
import hashlib
import hmac
import json
import tempfile
import time
import unittest
import uuid
from dataclasses import replace

import httpx
from cryptography.fernet import Fernet

from sonaweft_web.errors import BillingError
from sonaweft_web.ledger import Ledger as BookLedger
from sonaweft_web.errors import DomainError as BookError
from sonaweft_web.config import Settings
from sonaweft_web.paddle import PaddleCreditProvider
from sonaweft_web.payments import reconcile_paddle

TXN = "txn_" + "a" * 26
PRICE5, PRICE10 = "pri_" + "b" * 26, "pri_" + "c" * 26
PRODUCT = "pro_" + "d" * 26
EVENT = "evt_" + "e" * 26


class PaddleTests(unittest.TestCase):
    def setUp(self):
        self.owner = str(uuid.uuid4())
        self.s = Settings(
            Fernet.generate_key().decode(),
            billing_provider="paddle",
            billing_mode="live",
            paddle_api_key="synthetic-server-key",
            paddle_client_token="live_synthetic",
            paddle_product=PRODUCT,
            paddle_price5=PRICE5,
            paddle_price10=PRICE10,
            paddle_webhook_secret="synthetic-webhook-secret",
            paddle_checkout_url="https://testserver/checkout",
            paddle_approved=True,
            hosted_ready=True,
        )
        self.transaction = {
            "id": TXN,
            "status": "completed",
            "currency_code": "USD",
            "collection_mode": "automatic",
            "discount_id": None,
            "custom_data": {
                "app": "sonaweft",
                "owner": self.owner,
                "environment": "production",
            },
            "items": [
                {
                    "quantity": 1,
                    "price": {
                        "id": PRICE5,
                        "product_id": PRODUCT,
                        "billing_cycle": None,
                        "unit_price": {"amount": "500", "currency_code": "USD"},
                    },
                }
            ],
            "details": {
                "totals": {"subtotal": "500", "discount": "0", "currency_code": "USD"}
            },
        }
        self.adjustments = []
        self.requests = []
        self.tmp = tempfile.TemporaryDirectory()
        self.db = BookLedger(self.tmp.name + "/ledger.sqlite")
        self.db.payment_intent(TXN, self.owner, 50000)

        async def store(op, args):
            return getattr(self.db, op)(**args)

        self.store = store
        self.provider = PaddleCreditProvider(self.s, httpx.MockTransport(self.respond))

    def tearDown(self):
        self.tmp.cleanup()

    def respond(self, request):
        self.requests.append(request)
        if request.url.path == "/adjustments":
            return httpx.Response(
                200,
                json={
                    "data": self.adjustments,
                    "meta": {"pagination": {"has_more": False}},
                },
            )
        if request.method == "POST":
            return httpx.Response(201, json={"data": {"id": TXN}})
        return httpx.Response(200, json={"data": self.transaction})

    def order(self):
        return asyncio.run(self.provider.order(TXN))

    def event(self, event_type="transaction.completed", timestamp=None):
        payload = {
            "event_id": EVENT,
            "event_type": event_type,
            "data": {"id": TXN}
            if event_type.startswith("transaction.")
            else {"transaction_id": TXN},
        }
        raw = json.dumps(payload).encode()
        ts = int(time.time()) if timestamp is None else timestamp
        digest = hmac.new(
            self.s.paddle_webhook_secret.encode(),
            str(ts).encode() + b":" + raw,
            hashlib.sha256,
        ).hexdigest()
        return raw, f"ts={ts};h1={digest}"

    def adjustment(self, amount="200", action="refund", status="approved", n="f"):
        return {
            "id": "adj_" + n * 26,
            "transaction_id": TXN,
            "currency_code": "USD",
            "action": action,
            "status": status,
            "totals": {"subtotal": amount, "currency_code": "USD"},
        }

    def test_completed_pack_and_partial_refunds_exclude_tax(self):
        self.assertEqual(self.order()["units"], 50000)
        self.adjustments = [
            self.adjustment(),
            self.adjustment("0", n="g"),
            self.adjustment("300", status="pending_approval", n="h"),
        ]
        self.assertEqual(self.order()["revoked"], 20000)
        self.assertEqual(str(self.requests[-1].url.params["transaction_id"]), TXN)

    def test_rejects_wrong_currency_price_quantity_owner_environment_and_discount(self):
        original = json.dumps(self.transaction)
        for mutation in (
            lambda t: t.update(currency_code="EUR"),
            lambda t: t["items"][0]["price"].update(id=PRICE10),
            lambda t: t["items"][0].update(quantity=2),
            lambda t: t["items"][0]["price"].update(product_id="pro_" + "z" * 26),
            lambda t: t["items"][0]["price"].update(
                billing_cycle={"interval": "month"}
            ),
            lambda t: t["custom_data"].update(owner="invalid"),
            lambda t: t["custom_data"].update(environment="sandbox"),
            lambda t: t.update(discount_id="dsc_" + "x" * 26),
            lambda t: t["details"]["totals"].update(discount="100"),
        ):
            self.transaction = json.loads(original)
            mutation(self.transaction)
            with self.assertRaises(BillingError):
                self.order()

    def test_pending_transaction_cannot_fund_account(self):
        self.transaction["status"] = "paid"
        self.assertEqual(self.order()["status"], "paid")
        self.assertEqual(
            asyncio.run(reconcile_paddle(self.provider, self.store, TXN)), "paid"
        )
        self.assertEqual(self.db.account(self.owner)["available"], 0)

    def test_replay_refund_and_reordering_never_regrant(self):
        for amount in ("0", "200", "500", "0"):
            self.adjustments = [self.adjustment(amount)]
            asyncio.run(reconcile_paddle(self.provider, self.store, TXN))
        self.assertEqual(self.db.account(self.owner)["available"], 0)
        self.assertEqual(len(self.db.purchase_list()), 1)

    def test_fresh_api_owner_must_match_server_intent(self):
        self.transaction["custom_data"]["owner"] = str(uuid.uuid4())
        with self.assertRaises(BillingError):
            asyncio.run(reconcile_paddle(self.provider, self.store, TXN))
        self.assertEqual(self.db.purchase_list(), [])

    def test_signature_raw_body_timing_rotation_and_invalid_events(self):
        raw, signature = self.event()
        self.assertEqual(self.provider.webhook(raw, signature)["transaction_id"], TXN)
        self.assertIsNotNone(self.provider.webhook(raw, signature + ";h1=" + "0" * 64))
        for body, sig in (
            (raw + b" ", signature),
            self.event(timestamp=int(time.time()) - 301),
            self.event(timestamp=int(time.time()) + 301),
            (raw, ""),
        ):
            with self.assertRaises(BillingError):
                self.provider.webhook(body, sig)

    def test_checkout_has_server_owned_fixed_pack_and_no_customer_data(self):
        result = asyncio.run(self.provider.checkout(self.owner, 5))
        self.assertEqual(result["transaction_id"], TXN)
        self.assertEqual(result["url"], "https://testserver/checkout?_ptxn=" + TXN)
        body = json.loads(self.requests[-1].content)
        self.assertEqual(body["items"], [{"price_id": PRICE5, "quantity": 1}])
        self.assertEqual(body["custom_data"]["owner"], self.owner)
        self.assertNotIn("customer", body)
        with self.assertRaises(BillingError):
            asyncio.run(self.provider.checkout(self.owner, True))

    def test_disabled_and_sandbox_cannot_activate_public_billing(self):
        self.assertTrue(self.s.billing_ready)
        for s in (
            replace(self.s, paddle_approved=False),
            replace(self.s, billing_mode="test"),
            replace(self.s, paddle_environment="sandbox"),
            replace(self.s, paddle_price10=PRICE5),
        ):
            self.assertFalse(s.billing_ready)

    def test_inbox_durable_replay_and_payload_collision(self):
        self.db.payment_event(EVENT, TXN, "transaction.completed")
        self.db.payment_event(EVENT, TXN, "transaction.completed")
        reopened = BookLedger(self.tmp.name + "/ledger.sqlite")
        self.assertEqual(len(reopened.payment_pending()), 1)
        with self.assertRaises(BookError):
            reopened.payment_event(EVENT, "txn_" + "z" * 26, "transaction.completed")
        reopened.payment_done(EVENT)
        reopened.payment_event(EVENT, TXN, "transaction.completed")
        self.assertEqual(reopened.payment_pending(), [])
        self.assertEqual(reopened.operations()["pending_payments"], 0)

    def test_adjustment_pagination_must_fail_closed(self):
        def response(req):
            if req.url.path == "/adjustments":
                return httpx.Response(
                    200,
                    json={
                        "data": [],
                        "meta": {
                            "pagination": {
                                "has_more": True,
                                "next": "https://untrusted.invalid/",
                            }
                        },
                    },
                )
            return self.respond(req)

        self.provider.transport = httpx.MockTransport(response)
        with self.assertRaises(BillingError):
            self.order()

    def test_provider_outage_keeps_event_pending_and_balance_unfunded(self):
        from sonaweft_web.payments import process_paddle_events

        self.db.payment_event(EVENT, TXN, "transaction.completed")
        self.provider.transport = httpx.MockTransport(lambda req: httpx.Response(503))
        self.assertEqual(
            asyncio.run(process_paddle_events(self.provider, self.store)), 0
        )
        self.assertEqual(self.db.account(self.owner)["available"], 0)
        self.assertEqual(len(self.db.payment_pending()), 1)
        self.provider.transport = httpx.MockTransport(self.respond)
        self.assertEqual(
            asyncio.run(process_paddle_events(self.provider, self.store)), 1
        )
        self.assertEqual(self.db.account(self.owner)["available"], 50000)
        self.assertEqual(self.db.payment_pending(), [])

    def test_chargeback_revokes_full_pack_and_foreign_adjustments_are_rejected(self):
        self.adjustments = [self.adjustment("500", action="chargeback")]
        self.assertEqual(self.order()["revoked"], 50000)
        self.adjustments[0]["transaction_id"] = "txn_" + "z" * 26
        with self.assertRaises(BillingError):
            self.order()


class PaddleRouteTests(unittest.TestCase):
    setUp = PaddleTests.setUp
    tearDown = PaddleTests.tearDown
    respond = PaddleTests.respond
    event = PaddleTests.event
    adjustment = PaddleTests.adjustment

    def client(self, dispatch=None):
        async def noop(*args):
            pass

        app = create_app(
            self.s,
            self.store,
            noop,
            noop,
            provider=self.provider,
            payment_dispatcher=dispatch,
        )
        return TestClient(app, base_url="https://testserver")

    def test_checkout_requires_recovery_and_is_bound_to_session(self):
        with self.client() as c:
            csrf = c.get("/api/session").json()["csrf"]
            headers = {"X-CSRF-Token": csrf}
            self.assertEqual(
                c.post(
                    "/api/checkout",
                    json={"pack": 5, "terms_accepted": True},
                    headers=headers,
                ).status_code,
                409,
            )
            self.assertEqual(
                c.post("/api/recovery", json={}, headers=headers).status_code, 200
            )
            self.db = BookLedger(self.tmp.name + "/checkout.sqlite")
            # A separate store lets this test bind the server-created transaction.
            key = c.post("/api/recovery", json={}, headers=headers).json()[
                "recovery_key"
            ]
            self.owner = self.db.recover(
                hmac.new(
                    self.s.session_key.encode(),
                    ("recover:" + key).encode(),
                    hashlib.sha256,
                ).hexdigest()
            )
            self.transaction["custom_data"]["owner"] = self.owner
            self.assertEqual(
                c.post("/api/checkout", json={"pack": 5}, headers=headers).status_code,
                400,
            )
            result = c.post(
                "/api/checkout",
                json={"pack": 5, "terms_accepted": True},
                headers=headers,
            )
            self.assertEqual(result.status_code, 200)
            status = c.post(
                "/api/payment-status", json={"transaction_id": TXN}, headers=headers
            )
            self.assertEqual(status.json()["status"], "completed")
            self.assertEqual(self.db.account(self.owner)["available"], 50000)
            self.assertEqual(
                c.post(
                    "/api/access", json={"license_key": TXN}, headers=headers
                ).status_code,
                404,
            )
        with self.client() as other:
            csrf = other.get("/api/session").json()["csrf"]
            self.assertEqual(
                other.post(
                    "/api/payment-status",
                    json={"transaction_id": TXN},
                    headers={"X-CSRF-Token": csrf},
                ).status_code,
                404,
            )

    def test_signed_event_durable_even_when_dispatch_fails(self):
        async def unavailable():
            raise RuntimeError("fixture outage")

        raw, sig = self.event()
        with self.client(unavailable) as c:
            r = c.post(
                "/api/payment-event", content=raw, headers={"Paddle-Signature": sig}
            )
            self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.db.payment_pending()), 1)
        self.assertTrue(asyncio.run(reconcile_paddle(self.provider, self.store, TXN)))

    def test_webhook_verifies_api_and_deduplicates(self):
        raw, sig = self.event()
        with self.client() as c:
            for _ in range(2):
                self.assertEqual(
                    c.post(
                        "/api/payment-event",
                        content=raw,
                        headers={"Paddle-Signature": sig},
                    ).status_code,
                    200,
                )
            self.assertEqual(
                c.post(
                    "/api/payment-event",
                    content=raw,
                    headers={"Paddle-Signature": "bad"},
                ).status_code,
                400,
            )
        self.assertEqual(self.db.account(self.owner)["available"], 50000)
        self.assertEqual(self.db.payment_pending(), [])

    def test_other_product_notifications_do_not_poison_sonaweft_queue(self):
        self.db = BookLedger(self.tmp.name + "/other-product.sqlite")
        raw, sig = self.event()
        with self.client() as c:
            response = c.post(
                "/api/payment-event", content=raw, headers={"Paddle-Signature": sig}
            )
            self.assertTrue(response.json()["ignored"])
        self.assertEqual(self.db.payment_pending(), [])
        self.assertEqual(self.db.purchase_list(), [])

    def test_returning_to_refunded_checkout_does_not_show_fresh_credit(self):
        with self.client() as c:
            session = c.get("/api/session").json()
            # Restore the checkout's real owner through the existing private key flow.
            self.db.set_recovery(
                self.owner,
                hmac.new(
                    self.s.session_key.encode(), b"recover:" + b"r" * 40, hashlib.sha256
                ).hexdigest(),
            )
            c.post(
                "/api/restore",
                json={"recovery_key": "r" * 40},
                headers={"X-CSRF-Token": session["csrf"]},
            )
            csrf = c.get("/api/session").json()["csrf"]
            for amount, status in (
                ("200", "partially_refunded"),
                ("500", "refunded"),
                ("0", "refunded"),
            ):
                self.adjustments = [self.adjustment(amount)]
                result = c.post(
                    "/api/payment-status",
                    json={"transaction_id": TXN},
                    headers={"X-CSRF-Token": csrf},
                )
                self.assertEqual(result.json()["status"], status)
            self.assertEqual(self.db.account(self.owner)["available"], 0)

    def test_external_checkout_code_isolated_from_recording_workspace(self):
        with self.client() as c:
            workspace, checkout = c.get("/"), c.get("/checkout")
            self.assertNotIn(
                "cdn.paddle.com", workspace.headers["Content-Security-Policy"]
            )
            self.assertIn("cdn.paddle.com", checkout.headers["Content-Security-Policy"])
            self.assertIn("/static/checkout.js", checkout.text)
            self.assertNotIn("synthetic-server-key", checkout.text)
            for path in ("/pricing", "/terms", "/privacy", "/refunds"):
                self.assertEqual(c.get(path).status_code, 200)
