import hashlib
import hmac

from app.core.exceptions import InvalidWebhookSignature


def verify_signature(body: bytes, signature: str | None, secret: str) -> None:
    """
    Validate the hex HMAC-SHA256 signature of the unmodified request body.
    """
    if not signature:
        raise InvalidWebhookSignature

    expected = hmac.new(
        secret.encode("utf-8"),
        body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(
        expected.encode("ascii"),
        signature.encode("utf-8")
    ):
        raise InvalidWebhookSignature
