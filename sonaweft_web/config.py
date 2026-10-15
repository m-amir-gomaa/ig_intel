from dataclasses import dataclass
import os, re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    session_key: str
    billing_mode: str = "test"
    billing_provider: str = "paddle"
    paddle_environment: str = "production"
    paddle_api_key: str = ""
    paddle_client_token: str = ""
    paddle_product: str = ""
    paddle_price5: str = ""
    paddle_price10: str = ""
    paddle_webhook_secret: str = ""
    paddle_checkout_url: str = ""
    paddle_approved: bool = False
    hosted_ready: bool = False
    max_bytes: int = 64 * 1024 * 1024
    max_seconds: int = 3600
    trial_seconds: int = 30
    retention_seconds: int = 48 * 3600

    @property
    def payment_configured(self):
        u = urlsplit(self.paddle_checkout_url)
        return bool(
            self.paddle_environment in ("production", "sandbox")
            and self.paddle_api_key
            and self.paddle_client_token
            and self.paddle_webhook_secret
            and re.fullmatch(r"pro_[a-z0-9]{26}", self.paddle_product)
            and all(
                re.fullmatch(r"pri_[a-z0-9]{26}", p)
                for p in (self.paddle_price5, self.paddle_price10)
            )
            and self.paddle_price5 != self.paddle_price10
            and u.scheme == "https"
            and u.hostname
            and not u.username
            and not u.password
            and u.path == "/checkout"
            and not u.query
            and not u.fragment
        )

    @property
    def billing_ready(self):
        return (
            self.billing_mode == "live"
            and self.paddle_environment == "production"
            and self.paddle_approved
            and self.payment_configured
            and self.hosted_ready
        )

    @classmethod
    def from_env(cls):
        return cls(
            session_key=os.environ.get("SONAWEFT_SESSION_KEY", ""),
            billing_mode=os.environ.get("BILLING_MODE", "test"),
            paddle_environment=os.environ.get("PADDLE_ENVIRONMENT", "production"),
            paddle_api_key=os.environ.get("PADDLE_API_KEY", ""),
            paddle_client_token=os.environ.get("PADDLE_CLIENT_TOKEN", ""),
            paddle_product=os.environ.get("PADDLE_PRODUCT_ID", ""),
            paddle_price5=os.environ.get("PADDLE_PRICE_5", ""),
            paddle_price10=os.environ.get("PADDLE_PRICE_10", ""),
            paddle_webhook_secret=os.environ.get("PADDLE_WEBHOOK_SECRET", ""),
            paddle_checkout_url=os.environ.get("PADDLE_CHECKOUT_URL", ""),
            paddle_approved=os.environ.get("PADDLE_SELLER_APPROVED") == "true",
            hosted_ready=os.environ.get("SONAWEFT_HOSTED_READY") == "true",
        )


def quote(seconds, review="none"):
    import math

    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (float, int))
        or not math.isfinite(seconds)
        or not 0 < seconds <= 3600
        or review not in ("none", "standard", "advanced")
    ):
        raise ValueError(
            "Choose valid media up to 60 minutes and a supported review mode."
        )
    minutes = max(1, math.ceil(seconds / 60))
    # Service tariff, not a promise to pass through exact upstream costs.
    return {
        "units": 1500
        + minutes * 150
        + (
            {
                "none": 0,
                "standard": 1000 + minutes * 50,
                "advanced": 2000 + minutes * 100,
            }[review]
        ),
        "minutes": minutes,
        "review": review,
    }
