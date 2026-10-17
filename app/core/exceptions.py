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
