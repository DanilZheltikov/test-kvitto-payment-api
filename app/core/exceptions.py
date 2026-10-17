class InvalidPromoCode(Exception):
    """The requested promo code is not supported."""

    def __init__(self, promo_code: str) -> None:
        self.promo_code = promo_code
        super().__init__("Unknown promo code")


class InvalidInstallmentMonths(Exception):
    """The installment term is missing or invalid for the payment method."""

    def __init__(self, months: int | None, message: str) -> None:
        self.months = months
        super().__init__(message)


class PaymentNotFound(Exception):
    """The requested payment does not exist."""


class TariffNotFound(Exception):
    """The requested tariff does not exist."""

    def __init__(self, tariff_id: int) -> None:
        self.tariff_id = tariff_id
        super().__init__(f"Tariff {tariff_id} does not exist")


class InvalidTransition(Exception):
    """The requested payment status transition is not allowed."""


class InvalidWebhookSignature(Exception):
    """The webhook signature is missing or invalid."""
