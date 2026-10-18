from app.schemas.types import PaymentStatus

UNIQUE_VIOLATION_CODE = "23505"
NAME_IDEMPOTENCY_KEY_CONSTRAINT = "uq_payments_idempotency_key"

DEFAULT_DISCOUNT_PERCENT = 0
PROMO_DISCOUNTS_PERCENT = {"KVITTO10": 10}

DEFAULT_TARIFFS = {
    "basic": 990000,
    "standard": 1990000,
    "premium": 2990000,
}

ALLOWED_TRANSITIONS = {
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}
    ),
    PaymentStatus.SUCCEEDED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}
