from datetime import datetime
from uuid import UUID

import pytest
from fastapi import status
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.tariff import Tariff


PAYMENTS_URL = "/api/v1/payments"
TEST_EMAIL = "customer@example.com"
IDEMPOTENCY_KEY = "payment-test-key"
OTHER_IDEMPOTENCY_KEY = "another-payment-test-key"
MISSING_PAYMENT_ID = UUID("00000000-0000-0000-0000-000000000001")

PRICE = 1_990_000
DISCOUNT = 199_000
DISCOUNTED_PRICE = 1_791_000

SCHEDULES = {
    (False, 3): [663_334, 663_333, 663_333],
    (False, 6): [331_667] * 4 + [331_666] * 2,
    (False, 12): [165_834] * 4 + [165_833] * 8,
    (True, 3): [597_000] * 3,
    (True, 6): [298_500] * 6,
    (True, 12): [149_250] * 12,
}

PaymentPayload = dict[str, str | int | float | None]


@pytest.fixture
async def tariff(db_session: AsyncSession) -> Tariff:
    return (
        await db_session.scalars(
            select(Tariff).where(Tariff.title == "standard")
        )
    ).one()


@pytest.fixture
def payment_payload(tariff: Tariff) -> PaymentPayload:
    return {
        "tariff_id": tariff.id,
        "email": TEST_EMAIL,
        "method": "card",
    }


async def payment_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Payment))


async def assert_payment_created(
    response: Response,
    session: AsyncSession,
    payload: PaymentPayload,
    *,
    amount: int,
    discount: int,
    months: int | None = None,
    schedule: list[int] | None = None,
) -> None:
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    payment_id = UUID(body["id"])
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.tzinfo is not None

    expected = {
        "status": "pending",
        "tariff_id": payload["tariff_id"],
        "email": payload["email"],
        "method": payload["method"],
        "amount": amount,
        "discount": discount,
        "installment_months": months,
        "schedule": schedule,
    }
    assert body == {
        "id": str(payment_id),
        "created_at": body["created_at"],
        **expected
    }

    stored = await session.get(Payment, payment_id, populate_existing=True)
    assert stored is not None
    assert {field: getattr(stored, field) for field in expected} == expected
    assert stored.created_at == created_at
    assert stored.idempotency_key is None
    assert await payment_count(session) == 1

    if schedule is not None:
        assert len(schedule) == months
        assert sum(schedule) == amount


async def assert_payment_rejected(
    response: Response,
    session: AsyncSession,
    location: list[str],
    error_type: str | None = None,
) -> None:
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    errors = response.json()["detail"]
    assert any(
        error["loc"] == location
        and (error_type is None or error["type"] == error_type)
        for error in errors
    )
    assert await payment_count(session) == 0


@pytest.mark.parametrize("method", ["card", "sbp"])
@pytest.mark.parametrize("promo_code", [None, "KVITTO10", "kvitto10"])
async def test_create_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    method: str,
    promo_code: str | None,
) -> None:
    payment_payload["method"] = method
    if promo_code is not None:
        payment_payload["promo_code"] = promo_code

    response = await client.post(PAYMENTS_URL, json=payment_payload)
    discounted = promo_code is not None
    await assert_payment_created(
        response,
        db_session,
        payment_payload,
        amount=DISCOUNTED_PRICE if discounted else PRICE,
        discount=DISCOUNT if discounted else 0,
    )


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("promo_code", [None, "KVITTO10", "kvitto10"])
async def test_create_installment(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months: int,
    promo_code: str | None,
) -> None:
    payment_payload.update(method="installment", installment_months=months)
    if promo_code is not None:
        payment_payload["promo_code"] = promo_code

    response = await client.post(PAYMENTS_URL, json=payment_payload)
    discounted = promo_code is not None
    await assert_payment_created(
        response,
        db_session,
        payment_payload,
        amount=DISCOUNTED_PRICE if discounted else PRICE,
        discount=DISCOUNT if discounted else 0,
        months=months,
        schedule=SCHEDULES[(discounted, months)],
    )


async def test_create_payment_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
) -> None:
    headers = {"Idempotency-Key": IDEMPOTENCY_KEY}
    first = await client.post(
        PAYMENTS_URL,
        json=payment_payload,
        headers=headers
    )
    second = await client.post(
        PAYMENTS_URL,
        json=payment_payload,
        headers=headers
    )

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_200_OK
    assert second.json() == first.json()

    payments = (await db_session.scalars(select(Payment))).all()
    assert len(payments) == 1
    assert payments[0].id == UUID(first.json()["id"])
    assert payments[0].idempotency_key == IDEMPOTENCY_KEY


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        (None, None),
        (IDEMPOTENCY_KEY, OTHER_IDEMPOTENCY_KEY),
    ],
)
async def test_create_separate_payments(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    first_key: str | None,
    second_key: str | None,
) -> None:
    ids = []
    for key in (first_key, second_key):
        headers = {"Idempotency-Key": key} if key is not None else {}
        response = await client.post(
            PAYMENTS_URL,
            json=payment_payload,
            headers=headers
        )
        assert response.status_code == status.HTTP_201_CREATED
        ids.append(UUID(response.json()["id"]))

    assert ids[0] != ids[1]
    payments = (await db_session.scalars(select(Payment))).all()
    assert len(payments) == 2
    assert {p.id for p in payments} == set(ids)
    assert {p.id: p.idempotency_key for p in payments} == {
        ids[0]: first_key,
        ids[1]: second_key,
    }


async def test_get_payment(
    client: AsyncClient,
    payment_payload: PaymentPayload
) -> None:
    created = await client.post(PAYMENTS_URL, json=payment_payload)
    assert created.status_code == status.HTTP_201_CREATED

    response = await client.get(f"{PAYMENTS_URL}/{created.json()['id']}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == created.json()


async def test_get_missing_payment(client: AsyncClient) -> None:
    response = await client.get(f"{PAYMENTS_URL}/{MISSING_PAYMENT_ID}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Payment not found"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tariff_id", 0),
        ("tariff_id", -1),
        ("tariff_id", "1"),
        ("email", "invalid"),
        ("method", "cash"),
        ("promo_code", "UNKNOWN"),
        ("promo_code", ""),
    ],
)
async def test_create_payment_rejects_invalid_field(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    field: str,
    value: str | int,
) -> None:
    payment_payload[field] = value
    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(response, db_session, ["body", field])


@pytest.mark.parametrize("months", [5, 3.1, "3"])
async def test_create_installment_rejects_invalid_months(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months: int | float | str,
) -> None:
    payment_payload.update(method="installment", installment_months=months)
    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(
        response=response,
        session=db_session,
        location=["body", "installment_months"]
    )


@pytest.mark.parametrize("months_fields", [{}, {"installment_months": None}])
async def test_create_installment_requires_months(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months_fields: PaymentPayload,
) -> None:
    payment_payload.update(method="installment", **months_fields)
    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(response, db_session, ["body"])


@pytest.mark.parametrize("method", ["card", "sbp"])
async def test_create_payment_rejects_months_without_installment(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    method: str,
) -> None:
    payment_payload.update(method=method, installment_months=3)
    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(response, db_session, ["body"])


@pytest.mark.parametrize("field", ["tariff_id", "email", "method"])
async def test_create_payment_requires_field(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    field: str,
) -> None:
    del payment_payload[field]
    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(
        response=response,
        session=db_session,
        location=["body", field],
        error_type="missing"
    )


async def test_create_payment_rejects_missing_tariff(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
) -> None:
    max_tariff_id = await db_session.scalar(select(func.max(Tariff.id)))
    assert max_tariff_id is not None
    payment_payload["tariff_id"] = max_tariff_id + 1

    response = await client.post(PAYMENTS_URL, json=payment_payload)
    await assert_payment_rejected(response, db_session, ["body", "tariff_id"])
    assert any(
        error.get("input") == payment_payload["tariff_id"]
        for error in response.json()["detail"]
    )
