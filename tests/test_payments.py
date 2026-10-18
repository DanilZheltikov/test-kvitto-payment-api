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
TARIFF_TITLE = "standard"
TEST_EMAIL = "customer@example.com"
PROMO_CODE = "KVITTO10"
LOWERCASE_PROMO_CODE = "kvitto10"
IDEMPOTENCY_KEY = "payment-test-key"
OTHER_IDEMPOTENCY_KEY = "another-payment-test-key"
MISSING_PAYMENT_ID = UUID("00000000-0000-0000-0000-000000000001")

EXPECTED_AMOUNT = 1_990_000
EXPECTED_DISCOUNTED_AMOUNT = 1_791_000
EXPECTED_DISCOUNT = 199_000

EXPECTED_SCHEDULE_3_MONTHS = [663_334, 663_333, 663_333]
EXPECTED_SCHEDULE_6_MONTHS = [331_667] * 4 + [331_666] * 2
EXPECTED_SCHEDULE_12_MONTHS = [165_834] * 4 + [165_833] * 8
EXPECTED_DISCOUNTED_SCHEDULE_3_MONTHS = [597_000] * 3
EXPECTED_DISCOUNTED_SCHEDULE_6_MONTHS = [298_500] * 6
EXPECTED_DISCOUNTED_SCHEDULE_12_MONTHS = [149_250] * 12

PaymentPayload = dict[str, str | int | float | None]


@pytest.fixture
async def tariff(db_session: AsyncSession) -> Tariff:
    result = await db_session.scalars(
        select(Tariff).where(Tariff.title == TARIFF_TITLE)
    )
    return result.one()


@pytest.fixture
def payment_payload(tariff: Tariff) -> PaymentPayload:
    return {
        "tariff_id": tariff.id,
        "email": TEST_EMAIL,
        "method": "card",
    }


def assert_payment_response(
    response: Response,
    *,
    payload: PaymentPayload,
    expected_fields: dict[str, object],
) -> tuple[UUID, datetime, dict[str, object]]:
    body = response.json()
    payment_id = UUID(body["id"])
    created_at = datetime.fromisoformat(body["created_at"])

    assert created_at.tzinfo is not None, (
        f"Payment {payment_id}: expected a timezone-aware created_at, "
        f"got {body['created_at']!r}"
    )

    expected_record = {
        "status": "pending",
        "tariff_id": payload["tariff_id"],
        "email": payload["email"],
        "method": payload["method"],
        **expected_fields,
    }
    assert body == {
        "id": str(payment_id),
        "created_at": body["created_at"],
        **expected_record,
    }, (
        f"Payment {payment_id}: response fields do "
        "not match the expected payment"
    )

    return payment_id, created_at, expected_record


async def assert_payment_saved(
    db_session: AsyncSession,
    payment_id: UUID,
    created_at: datetime,
    expected_fields: dict[str, object],
) -> None:
    payment = await db_session.get(Payment, payment_id)

    assert payment is not None, (
        f"Payment {payment_id} was returned by the API "
        "but not found in the database"
    )

    for field, expected_value in expected_fields.items():
        actual_value = getattr(payment, field)

        assert actual_value == expected_value, (
            f"Stored payment {payment_id}: field {field!r} mismatch. "
            f"Expected {expected_value!r}, got {actual_value!r}"
        )

    assert payment.created_at == created_at, (
        f"Stored payment {payment_id}: expected created_at {created_at!r}, "
        f"got {payment.created_at!r}"
    )
    assert payment.idempotency_key is None, (
        f"Payment {payment_id} was created without an idempotency key; "
        f"expected None in the database, got {payment.idempotency_key!r}"
    )

    payment_count = await db_session.scalar(
        select(func.count()).select_from(Payment)
    )
    assert payment_count == 1, (
        f"Creating one payment must leave exactly one record; "
        f"found {payment_count} payment(s) in the database"
    )


async def assert_payment_rejected(
    response: Response,
    db_session: AsyncSession,
    *,
    error_location: list[str],
) -> None:

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (
        "Expected an invalid payment request to return 422; "
        f"got {response.status_code}. Response: {response.text}"
    )

    errors = response.json()["detail"]

    assert any(error["loc"] == error_location for error in errors), (
        f"Expected a validation error at {error_location!r}, got: {errors!r}"
    )

    payment_count = await db_session.scalar(
        select(func.count()).select_from(Payment)
    )
    assert payment_count == 0, (
        f"Rejected request must not create a payment; "
        f"found {payment_count} payment(s) in the database"
    )


@pytest.mark.parametrize("method", ["card", "sbp"])
async def test_create_payment_without_promo(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    method: str,
) -> None:
    payment_payload["method"] = method

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_201_CREATED, (
        "Expected payment creation to return 201; "
        f"got {response.status_code}. Response: {response.text}"
    )

    expected_fields = {
        "amount": EXPECTED_AMOUNT,
        "discount": 0,
        "installment_months": None,
        "schedule": None,
    }

    payment_id, created_at, expected_record = assert_payment_response(
        response,
        payload=payment_payload,
        expected_fields=expected_fields,
    )

    await assert_payment_saved(
        db_session, payment_id, created_at, expected_record,
    )


@pytest.mark.parametrize("method", ["card", "sbp"])
@pytest.mark.parametrize(
    "promo_code",
    [
        pytest.param(PROMO_CODE, id="uppercase-promo"),
        pytest.param(LOWERCASE_PROMO_CODE, id="lowercase-promo"),
    ],
)
async def test_create_payment_with_promo(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    method: str,
    promo_code: str,
) -> None:
    payment_payload["method"] = method
    payment_payload["promo_code"] = promo_code

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_201_CREATED, (
        "Expected payment creation to return 201; "
        f"got {response.status_code}. Response: {response.text}"
    )

    expected_fields = {
        "amount": EXPECTED_DISCOUNTED_AMOUNT,
        "discount": EXPECTED_DISCOUNT,
        "installment_months": None,
        "schedule": None,
    }

    payment_id, created_at, expected_record = assert_payment_response(
        response, payload=payment_payload, expected_fields=expected_fields,
    )

    await assert_payment_saved(
        db_session, payment_id, created_at, expected_record,
    )


@pytest.mark.parametrize(
    ("months", "expected_schedule"),
    [
        pytest.param(
            3, EXPECTED_SCHEDULE_3_MONTHS, id="three-months",
        ),
        pytest.param(
            6, EXPECTED_SCHEDULE_6_MONTHS, id="six-months",
        ),
        pytest.param(
            12, EXPECTED_SCHEDULE_12_MONTHS, id="twelve-months",
        ),
    ],
)
async def test_create_installment_without_promo(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months: int,
    expected_schedule: list[int],
) -> None:
    payment_payload["method"] = "installment"
    payment_payload["installment_months"] = months

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_201_CREATED, (
        "Expected payment creation to return 201; "
        f"got {response.status_code}. Response: {response.text}"
    )

    expected_fields = {
        "amount": EXPECTED_AMOUNT,
        "discount": 0,
        "installment_months": months,
        "schedule": expected_schedule,
    }

    payment_id, created_at, expected_record = assert_payment_response(
        response,
        payload=payment_payload,
        expected_fields=expected_fields,
    )

    body = response.json()
    schedule_length = len(body["schedule"])
    schedule_total = sum(body["schedule"])

    assert schedule_length == months, (
        f"Payment {payment_id}: expected {months} scheduled payments, "
        f"got {schedule_length}"
    )
    assert schedule_total == body["amount"], (
        f"Payment {payment_id}: expected schedule total {body['amount']}, "
        f"got {schedule_total}"
    )

    await assert_payment_saved(
        db_session=db_session,
        payment_id=payment_id,
        created_at=created_at,
        expected_fields=expected_record,
    )


@pytest.mark.parametrize(
    ("months", "expected_schedule"),
    [
        pytest.param(
            3, EXPECTED_DISCOUNTED_SCHEDULE_3_MONTHS, id="three-months",
        ),
        pytest.param(
            6, EXPECTED_DISCOUNTED_SCHEDULE_6_MONTHS, id="six-months",
        ),
        pytest.param(
            12, EXPECTED_DISCOUNTED_SCHEDULE_12_MONTHS, id="twelve-months",
        ),
    ],
)
@pytest.mark.parametrize(
    "promo_code",
    [
        pytest.param(PROMO_CODE, id="uppercase-promo"),
        pytest.param(LOWERCASE_PROMO_CODE, id="lowercase-promo"),
    ],
)
async def test_create_installment_with_promo(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months: int,
    expected_schedule: list[int],
    promo_code: str,
) -> None:
    payment_payload["method"] = "installment"
    payment_payload["installment_months"] = months
    payment_payload["promo_code"] = promo_code

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_201_CREATED, (
        "Expected payment creation to return 201; "
        f"got {response.status_code}. Response: {response.text}"
    )

    expected_fields = {
        "amount": EXPECTED_DISCOUNTED_AMOUNT,
        "discount": EXPECTED_DISCOUNT,
        "installment_months": months,
        "schedule": expected_schedule,
    }

    payment_id, created_at, expected_record = assert_payment_response(
        response=response,
        payload=payment_payload,
        expected_fields=expected_fields,
    )

    body = response.json()
    schedule_length = len(body["schedule"])
    schedule_total = sum(body["schedule"])

    assert schedule_length == months, (
        f"Payment {payment_id}: expected {months} scheduled payments, "
        f"got {schedule_length}"
    )
    assert schedule_total == body["amount"], (
        f"Payment {payment_id}: expected schedule total {body['amount']}, "
        f"got {schedule_total}"
    )

    await assert_payment_saved(
        db_session=db_session,
        payment_id=payment_id,
        created_at=created_at,
        expected_fields=expected_record,
    )


async def test_create_payment_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
) -> None:
    headers = {"Idempotency-Key": IDEMPOTENCY_KEY}

    first = await client.post(
        PAYMENTS_URL, json=payment_payload, headers=headers,
    )
    second = await client.post(
        PAYMENTS_URL, json=payment_payload, headers=headers,
    )

    assert first.status_code == status.HTTP_201_CREATED, (
        "Expected the first request with an idempotency key to return 201; "
        f"got {first.status_code}. Response: {first.text}"
    )
    assert second.status_code == status.HTTP_200_OK, (
        "Expected a repeated request with "
        "the same idempotency key to return 200; "
        f"got {second.status_code}. Response: {second.text}"
    )
    assert second.json() == first.json(), (
        "Repeating a request with the same idempotency key "
        "must return the original payment unchanged"
    )

    payments = (await db_session.scalars(select(Payment))).all()

    assert len(payments) == 1, (
        "Two requests with the same idempotency key must create one payment; "
        f"found {len(payments)} records"
    )

    expected_payment_id = UUID(first.json()["id"])

    assert payments[0].id == expected_payment_id, (
        f"Expected stored payment ID {expected_payment_id}, "
        f"got {payments[0].id}"
    )
    assert payments[0].idempotency_key == IDEMPOTENCY_KEY, (
        f"Payment {payments[0].id}: expected stored idempotency key "
        f"{IDEMPOTENCY_KEY!r}, got {payments[0].idempotency_key!r}"
    )


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        pytest.param(None, None, id="without-keys"),
        pytest.param(
            IDEMPOTENCY_KEY, OTHER_IDEMPOTENCY_KEY, id="different-keys",
        ),
    ],
)
async def test_create_separate_payments(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    first_key: str | None,
    second_key: str | None,
) -> None:
    payment_ids = []

    for key in (first_key, second_key):
        headers = {"Idempotency-Key": key} if key is not None else {}
        response = await client.post(
            PAYMENTS_URL,
            json=payment_payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_201_CREATED, (
            "Expected payment creation to return 201; "
            f"got {response.status_code}. Response: {response.text}"
        )

        payment_ids.append(UUID(response.json()["id"]))

    assert payment_ids[0] != payment_ids[1], (
        f"Requests with keys {first_key!r} and {second_key!r} "
        f"must create distinct payments; both returned {payment_ids[0]}"
    )

    payments = (await db_session.scalars(select(Payment))).all()

    assert len(payments) == 2, (
        f"Requests with keys {first_key!r} and {second_key!r} "
        f"must create two payments; found {len(payments)} records"
    )
    assert {payment.id for payment in payments} == set(payment_ids), (
        "Stored payment IDs do not match the IDs returned by both requests"
    )
    assert {payment.id: payment.idempotency_key for payment in payments} == {
        payment_ids[0]: first_key,
        payment_ids[1]: second_key,
    }, "Stored idempotency keys do not match the keys used for each payment"


async def test_get_payment(
    client: AsyncClient,
    payment_payload: PaymentPayload,
) -> None:
    created = await client.post(PAYMENTS_URL, json=payment_payload)

    assert created.status_code == status.HTTP_201_CREATED, (
        "Expected setup payment creation to return 201; "
        f"got {created.status_code}. Response: {created.text}"
    )

    payment_id = created.json()["id"]

    response = await client.get(f"{PAYMENTS_URL}/{payment_id}")

    assert response.status_code == status.HTTP_200_OK, (
        "Expected payment retrieval to return 200; "
        f"got {response.status_code}. Response: {response.text}"
    )
    assert response.json() == created.json(), (
        f"Retrieving payment {payment_id} "
        "must return its original creation data"
    )


async def test_get_missing_payment(client: AsyncClient) -> None:
    response = await client.get(f"{PAYMENTS_URL}/{MISSING_PAYMENT_ID}")

    assert response.status_code == status.HTTP_404_NOT_FOUND, (
        "Expected a missing payment to return 404; "
        f"got {response.status_code}. Response: {response.text}"
    )
    assert response.json() == {"detail": "Payment not found"}, (
        f"Missing payment {MISSING_PAYMENT_ID}: unexpected error response"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("tariff_id", 0, id="zero-tariff-id"),
        pytest.param("tariff_id", -1, id="negative-tariff-id"),
        pytest.param("tariff_id", "1", id="string-tariff-id"),
        pytest.param("email", "invalid", id="invalid-email"),
        pytest.param("method", "cash", id="unknown-method"),
        pytest.param("promo_code", "UNKNOWN", id="unknown-promo"),
        pytest.param("promo_code", "", id="empty-promo"),
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

    await assert_payment_rejected(
        response=response,
        db_session=db_session,
        error_location=["body", field],
    )


@pytest.mark.parametrize(
    "months",
    [
        pytest.param(5, id="unsupported-months"),
        pytest.param(3.1, id="fractional-months"),
        pytest.param("3", id="string-months"),
    ],
)
async def test_create_installment_rejects_invalid_months(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months: int | float | str,
) -> None:
    payment_payload["method"] = "installment"
    payment_payload["installment_months"] = months

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    await assert_payment_rejected(
        response=response,
        db_session=db_session,
        error_location=["body", "installment_months"],
    )


@pytest.mark.parametrize(
    "months_fields",
    [
        pytest.param({}, id="missing-months"),
        pytest.param({"installment_months": None}, id="null-months"),
    ],
)
async def test_create_installment_requires_months(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    months_fields: PaymentPayload,
) -> None:
    payment_payload["method"] = "installment"
    payment_payload.update(months_fields)

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    await assert_payment_rejected(
        response=response,
        db_session=db_session,
        error_location=["body"],
    )


@pytest.mark.parametrize("method", ["card", "sbp"])
async def test_create_payment_rejects_months_without_installment(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    method: str,
) -> None:
    payment_payload["method"] = method
    payment_payload["installment_months"] = 3

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    await assert_payment_rejected(
        response=response,
        db_session=db_session,
        error_location=["body"],
    )


@pytest.mark.parametrize("field", ["tariff_id", "email", "method"])
async def test_create_payment_requires_field(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
    field: str,
) -> None:
    del payment_payload[field]

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (
        "Expected an invalid payment request to return 422; "
        f"got {response.status_code}. Response: {response.text}"
    )
    errors = response.json()["detail"]
    assert any(
        error["loc"] == ["body", field] and error["type"] == "missing"
        for error in errors
    ), (
        f"Expected a 'missing' validation error at {['body', field]!r}, "
        f"got: {errors!r}"
    )
    payment_count = await db_session.scalar(
        select(func.count()).select_from(Payment)
    )
    assert payment_count == 0, (
        f"Rejected request must not create a payment; "
        f"found {payment_count} payment(s) in the database"
    )


async def test_create_payment_rejects_missing_tariff(
    client: AsyncClient,
    db_session: AsyncSession,
    payment_payload: PaymentPayload,
) -> None:
    max_tariff_id = await db_session.scalar(select(func.max(Tariff.id)))

    assert max_tariff_id is not None, (
        "Test setup requires at least one seeded tariff; "
        "the tariff table is empty"
    )

    payment_payload["tariff_id"] = max_tariff_id + 1

    response = await client.post(PAYMENTS_URL, json=payment_payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (
        "Expected an invalid payment request to return 422; "
        f"got {response.status_code}. Response: {response.text}"
    )

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "tariff_id"]
        and error["input"] == payment_payload["tariff_id"]
        for error in errors
    ), (
        "Expected a validation error at ['body', 'tariff_id'] "
        f"with input {payment_payload['tariff_id']!r}, got: {errors!r}"
    )

    payment_count = await db_session.scalar(
        select(func.count()).select_from(Payment)
    )

    assert payment_count == 0, (
        f"Rejected request must not create a payment; "
        f"found {payment_count} payment(s) in the database"
    )
