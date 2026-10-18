from datetime import datetime

import pytest
from fastapi import status
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.tariff import Tariff
from app.schemas.types import PaymentMethod, PaymentStatus

PAYMENTS_URL = "/api/v1/payments"
EMAILS = ("alice@example.com", "bob@example.com")


@pytest.fixture
async def payments(
    db_session: AsyncSession,
) -> dict[tuple[str, PaymentStatus], Payment]:
    tariff = (
        await db_session.scalars(
            select(Tariff).where(Tariff.title == "standard")
        )
    ).one()
    payments = {
        (email, payment_status): Payment(
            tariff_id=tariff.id,
            email=email,
            status=payment_status,
            method=PaymentMethod.CARD,
            amount=1_990_000,
            discount=0,
        )
        for email in EMAILS
        for payment_status in PaymentStatus
    }
    installment = payments[EMAILS[1], PaymentStatus.SUCCEEDED]
    installment.method = PaymentMethod.INSTALLMENT
    installment.amount = 1_791_000
    installment.discount = 199_000
    installment.installment_months = 3
    installment.schedule = [597_000] * 3

    db_session.add_all(payments.values())
    await db_session.commit()
    return payments


def assert_payment_list(response: Response, expected: list[Payment]) -> None:
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == len(expected)

    by_id = {str(payment.id): payment for payment in expected}
    assert {item["id"] for item in body} == set(by_id)
    for item in body:
        payment = by_id[item["id"]]
        assert item == {
            "id": str(payment.id),
            "status": payment.status.value,
            "tariff_id": payment.tariff_id,
            "email": payment.email,
            "method": payment.method.value,
            "amount": payment.amount,
            "discount": payment.discount,
            "installment_months": payment.installment_months,
            "schedule": payment.schedule,
            "created_at": item["created_at"],
        }
        assert datetime.fromisoformat(item["created_at"]) == payment.created_at
        assert type(item["amount"]) is int
        assert type(item["discount"]) is int
        if item["schedule"] is not None:
            assert all(type(amount) is int for amount in item["schedule"])


async def test_list_payments_empty(client: AsyncClient) -> None:
    response = await client.get(PAYMENTS_URL)
    assert_payment_list(response, [])


async def test_list_payments_without_filters(
    client: AsyncClient,
    payments: dict[tuple[str, PaymentStatus], Payment],
) -> None:
    response = await client.get(PAYMENTS_URL)
    assert_payment_list(response, list(payments.values()))


@pytest.mark.parametrize("email", EMAILS)
async def test_list_payments_by_email(
    client: AsyncClient,
    payments: dict[tuple[str, PaymentStatus], Payment],
    email: str,
) -> None:
    response = await client.get(PAYMENTS_URL, params={"email": email})
    expected = [
        payments[email, payment_status] for payment_status in PaymentStatus
    ]
    assert_payment_list(response, expected)


@pytest.mark.parametrize("payment_status", list(PaymentStatus))
async def test_list_payments_by_status(
    client: AsyncClient,
    payments: dict[tuple[str, PaymentStatus], Payment],
    payment_status: PaymentStatus,
) -> None:
    response = await client.get(
        PAYMENTS_URL, params={"status": payment_status.value},
    )
    expected = [payments[email, payment_status] for email in EMAILS]
    assert_payment_list(response, expected)


@pytest.mark.parametrize("email", EMAILS)
@pytest.mark.parametrize("payment_status", list(PaymentStatus))
async def test_list_payments_by_email_and_status(
    client: AsyncClient,
    payments: dict[tuple[str, PaymentStatus], Payment],
    email: str,
    payment_status: PaymentStatus,
) -> None:
    response = await client.get(
        PAYMENTS_URL, params={"email": email, "status": payment_status.value},
    )
    assert_payment_list(response, [payments[email, payment_status]])


@pytest.mark.parametrize(
    "params",
    [
        {"email": "missing@example.com"},
        {"email": "missing@example.com", "status": "succeeded"},
    ],
    ids=["email", "email-and-status"],
)
async def test_list_payments_without_matches(
    client: AsyncClient,
    payments: dict[tuple[str, PaymentStatus], Payment],
    params: dict[str, str],
) -> None:
    response = await client.get(PAYMENTS_URL, params=params)
    assert_payment_list(response, [])


@pytest.mark.parametrize(
    ("field", "value"), [("email", "invalid"), ("status", "unknown")],
)
async def test_list_payments_rejects_invalid_filter(
    client: AsyncClient,
    field: str,
    value: str,
) -> None:
    response = await client.get(PAYMENTS_URL, params={field: value})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert any(
        error["loc"] == ["query", field]
        for error in response.json()["detail"]
    )
