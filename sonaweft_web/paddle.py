"""Paddle Billing v1: server-created one-time packs, never client entitlements.

Docs: developer.paddle.com/api-reference/{transactions,adjustments} and
developer.paddle.com/webhooks/about/signature-verification. No Classic licensing.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from urllib.parse import urlencode, urlsplit

import httpx

from .errors import BillingError


def valid_id(value, prefix):
    return isinstance(value, str) and bool(
        re.fullmatch(prefix + r"_[a-z0-9]{26}", value)
    )


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}", value):
        raise BillingError("Payment amounts need review.")
    return int(value)


class PaddleCreditProvider:
    def __init__(self, settings, transport=None):
        self.s, self.transport = settings, transport
        self.base = (
            "https://sandbox-api.paddle.com"
            if settings.paddle_environment == "sandbox"
            else "https://api.paddle.com"
        )
        self.prefix = "paddle:" + settings.paddle_environment + ":"

    def ready(self):
        if not self.s.payment_configured or self.s.billing_mode not in ("live", "test"):
            raise BillingError("Processing payments are not configured.")

    async def request(self, method, path, **kwargs):
        self.ready()
        try:
            async with httpx.AsyncClient(
                timeout=12, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.request(
                    method,
                    self.base + path,
                    headers={
                        "Authorization": "Bearer " + self.s.paddle_api_key,
                        "Paddle-Version": "1",
                        "Accept": "application/json",
                    },
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            raise BillingError(
                "Payment verification is temporarily unavailable. No credits were added; retry shortly."
            ) from None

    async def checkout(self, owner, pack):
        if type(pack) is not int or pack not in (5, 10):
            raise BillingError("Choose a $5 or $10 processing pack.")
        try:
            if str(uuid.UUID(owner)) != owner:
                raise ValueError()
            result = await self.request(
                "POST",
                "/transactions",
                json={
                    "items": [
                        {
                            "price_id": self.s.paddle_price5
                            if pack == 5
                            else self.s.paddle_price10,
                            "quantity": 1,
                        }
                    ],
                    "currency_code": "USD",
                    "collection_mode": "automatic",
                    "discount_id": None,
                    "custom_data": {
                        "app": "sonaweft",
                        "owner": owner,
                        "environment": self.s.paddle_environment,
                    },
                    "checkout": {"url": self.s.paddle_checkout_url},
                },
            )
            txn = result["data"]["id"]
            if not valid_id(txn, "txn"):
                raise ValueError()
            return {
                "transaction_id": txn,
                "units": pack * 10000,
                "url": self.s.paddle_checkout_url + "?" + urlencode({"_ptxn": txn}),
            }
        except (ValueError, KeyError, TypeError):
            raise BillingError(
                "Checkout could not be verified. Try again shortly."
            ) from None

    async def order(self, transaction_id):
        if not valid_id(transaction_id, "txn"):
            raise BillingError("Invalid transaction.")
        try:
            t = (await self.request("GET", "/transactions/" + transaction_id))["data"]
            data = t["custom_data"]
            owner = data["owner"]
            items = t["items"]
            if (
                t["id"] != transaction_id
                or t["currency_code"] != "USD"
                or t["collection_mode"] != "automatic"
                or t.get("discount_id") is not None
                or data["app"] != "sonaweft"
                or data["environment"] != self.s.paddle_environment
                or str(uuid.UUID(owner)) != owner
                or len(items) != 1
            ):
                raise ValueError()
            item = items[0]
            price = item["price"]
            units = {self.s.paddle_price5: 50000, self.s.paddle_price10: 100000}[
                price["id"]
            ]
            cents = units // 100
            if (
                type(item["quantity"]) is not int
                or item["quantity"] != 1
                or price["product_id"] != self.s.paddle_product
                or price["billing_cycle"] is not None
                or price["unit_price"]["currency_code"] != "USD"
                or amount(price["unit_price"]["amount"]) != cents
            ):
                raise ValueError()
            status = t["status"]
            result = {
                "order_id": self.prefix + transaction_id,
                "transaction_id": transaction_id,
                "owner": owner,
                "units": units,
                "revoked": 0,
                "status": status,
            }
            if status in ("draft", "ready", "billed", "paid", "past_due", "canceled"):
                return result
            if status != "completed":
                raise ValueError()
            totals = t["details"]["totals"]
            if (
                totals["currency_code"] != "USD"
                or amount(totals["subtotal"]) != cents
                or amount(totals["discount"]) != 0
            ):
                raise ValueError()
            # Refunds can be paginated. Never assume the first page is complete,
            # and never follow provider data to another host with our API key.
            path = "/adjustments?" + urlencode(
                {"transaction_id": transaction_id, "per_page": 200}
            )
            refunded, seen, pages = 0, set(), set()
            for _ in range(20):
                if path in pages:
                    raise ValueError()
                pages.add(path)
                response = await self.request("GET", path)
                for adj in response["data"]:
                    if (
                        not valid_id(adj["id"], "adj")
                        or adj["transaction_id"] != transaction_id
                        or adj["currency_code"] != "USD"
                        or adj["totals"]["currency_code"] != "USD"
                    ):
                        raise ValueError()
                    if adj["id"] in seen:
                        continue
                    seen.add(adj["id"])
                    if adj["status"] == "approved" and adj["action"] in (
                        "refund",
                        "credit",
                        "chargeback",
                        "chargeback_warning",
                    ):
                        refunded += amount(adj["totals"]["subtotal"])
                pagination = response["meta"]["pagination"]
                if pagination["has_more"] is False:
                    break
                next_url = urlsplit(pagination["next"])
                if (
                    next_url.scheme != "https"
                    or next_url.netloc != urlsplit(self.base).netloc
                    or next_url.path != "/adjustments"
                    or next_url.fragment
                ):
                    raise ValueError()
                from urllib.parse import parse_qs

                if parse_qs(next_url.query).get("transaction_id") != [transaction_id]:
                    raise ValueError()
                path = next_url.path + "?" + next_url.query
            else:
                raise ValueError()
            result["revoked"] = min(units, (units * refunded + cents - 1) // cents)
            return result
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BillingError(
                "This payment does not match the processing pack. No credits were added."
            ) from None

    def webhook(self, body, signature):
        self.ready()
        try:
            if not isinstance(signature, str) or len(signature) > 2048:
                raise ValueError()
            fields = [field.strip().split("=", 1) for field in signature.split(";")]
            ts = [v for k, v in fields if k == "ts"]
            hashes = [v for k, v in fields if k == "h1"]
            if (
                len(ts) != 1
                or not re.fullmatch(r"[0-9]{10}", ts[0])
                or abs(time.time() - int(ts[0])) > 300
            ):
                raise ValueError()
            expected = hmac.new(
                self.s.paddle_webhook_secret.encode(),
                ts[0].encode() + b":" + body,
                hashlib.sha256,
            ).hexdigest()
            if not any(
                re.fullmatch(r"[a-f0-9]{64}", v) and hmac.compare_digest(expected, v)
                for v in hashes
            ):
                raise ValueError()
            event = json.loads(body)
            kind = event["event_type"]
            if kind not in (
                "transaction.completed",
                "adjustment.created",
                "adjustment.updated",
            ):
                return None
            txn = event["data"][
                "id" if kind == "transaction.completed" else "transaction_id"
            ]
            if not valid_id(event["event_id"], "evt") or not valid_id(txn, "txn"):
                raise ValueError()
            return {"event_id": event["event_id"], "transaction_id": txn, "kind": kind}
        except (KeyError, ValueError, TypeError):
            raise BillingError("Invalid payment signature or event.") from None
