"""Durable minimal payment inbox and checkout ownership, without customer payloads."""

import time

from .errors import BillingError


class PaymentLedger:
    def setup_payments(self, db):
        db.executescript("""
        CREATE TABLE IF NOT EXISTS payment_intents(transaction_id TEXT PRIMARY KEY,owner TEXT NOT NULL,units INTEGER NOT NULL,created REAL NOT NULL,terms_version TEXT NOT NULL DEFAULT '2026-10-15');
        CREATE TABLE IF NOT EXISTS payment_events(event_id TEXT PRIMARY KEY,transaction_id TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL,completed REAL);
        CREATE INDEX IF NOT EXISTS payment_events_pending ON payment_events(completed,created);
        """)

    def payment_intent(self, transaction_id, owner, units):
        from .errors import DomainError as BookError

        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO payment_intents(transaction_id,owner,units,created) VALUES (?,?,?,?)",
                (transaction_id, owner, units, time.time()),
            )
            row = db.execute(
                "SELECT owner,units FROM payment_intents WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row["owner"] != owner or row["units"] != units:
                raise BookError("Checkout ownership differs from its original request.")

    def payment_lookup(self, transaction_id):
        with self.db() as db:
            row = db.execute(
                "SELECT transaction_id,owner,units FROM payment_intents WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            return dict(row) if row else None

    def payment_receipt(self, order_id):
        with self.db() as db:
            row = db.execute(
                "SELECT revoked,granted FROM purchases WHERE order_id=?", (order_id,)
            ).fetchone()
            return dict(row) if row else None

    def payment_event(self, event_id, transaction_id, kind):
        from .errors import DomainError as BookError

        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO payment_events(event_id,transaction_id,kind,created) VALUES (?,?,?,?)",
                (event_id, transaction_id, kind, time.time()),
            )
            row = db.execute(
                "SELECT * FROM payment_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if row["transaction_id"] != transaction_id or row["kind"] != kind:
                raise BookError("Payment event differs from its original delivery.")
            return row["completed"] is None

    def payment_pending(self):
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT event_id,transaction_id,kind FROM payment_events WHERE completed IS NULL ORDER BY created LIMIT 50"
                )
            ]

    def payment_done(self, event_id):
        with self.db() as db:
            db.execute(
                "UPDATE payment_events SET completed=? WHERE event_id=?",
                (time.time(), event_id),
            )


async def reconcile_paddle(provider, store, transaction_id):
    intent = await store("payment_lookup", {"transaction_id": transaction_id})
    if not intent:
        raise BillingError(
            "This transaction has no Sonaweft checkout request. Contact support with your receipt."
        )
    purchase = await provider.order(transaction_id)
    if purchase["owner"] != intent["owner"] or purchase["units"] != intent["units"]:
        raise BillingError("Checkout ownership does not match. No credits were added.")
    if purchase["status"] != "completed":
        return purchase["status"]
    credited_owner = await store(
        "credit",
        {
            "owner": intent["owner"],
            "order_id": purchase["order_id"],
            "units": purchase["units"],
            "revoked": purchase["revoked"],
            "verified": True,
        },
    )
    if credited_owner != intent["owner"]:
        raise BillingError("Recorded purchase ownership needs review.")
    receipt = await store("payment_receipt", {"order_id": purchase["order_id"]})
    if receipt["revoked"] == receipt["granted"]:
        return "refunded"
    return "partially_refunded" if receipt["revoked"] else "completed"


async def process_paddle_events(provider, store):
    processed = 0
    for event in await store("payment_pending", {}):
        try:
            status = await reconcile_paddle(provider, store, event["transaction_id"])
            if status in ("completed", "refunded", "partially_refunded"):
                await store("payment_done", {"event_id": event["event_id"]})
                processed += 1
        except Exception:
            await store("event", {"kind": "reconcile_error"})
            # Preserve for another delivery/hourly retry; never log API payloads.
    return processed
