import asyncio
import hashlib
import hmac
import json
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import pytest
from fastapi import status
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.tariff import Tariff
from app.repositories.payment import payment_repository
from app.schemas.types import PaymentMethod, PaymentStatus


@pytest.fixture
async def tariff_id(db_session: AsyncSession) -> int:
    return (
        await db_session.scalars(
            select(Tariff.id).where(Tariff.title == "standard")
        )
    ).one()


async def concurrent_requests(
    *requests: Coroutine[Any, Any, Response],
) -> list[Response]:
    async with asyncio.timeout(10):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(request) for request in requests]
    return [task.result() for task in tasks]


async def test_concurrent_payments_with_same_key(
    client: AsyncClient,
    db_session: AsyncSession,
    tariff_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 3
    barrier = asyncio.Barrier(request_count)
    get_by_key = payment_repository.get_by_idempotency_key

    async def synchronized_lookup(
        session: AsyncSession, key: str,
    ) -> Payment | None:
        payment = await get_by_key(session, key)
        if payment is None:
            await barrier.wait()
        return payment

    monkeypatch.setattr(
        payment_repository, "get_by_idempotency_key", synchronized_lookup,
    )
    payload = {
        "tariff_id": tariff_id,
        "email": "customer@example.com",
        "method": "card",
    }
    responses = await concurrent_requests(*(
        client.post(
            "/api/v1/payments",
            json=payload,
            headers={"Idempotency-Key": "concurrent-payment"},
        )
        for _ in range(request_count)
    ))

    assert sorted(response.status_code for response in responses) == [
        status.HTTP_200_OK, status.HTTP_200_OK, status.HTTP_201_CREATED,
    ]
    body = responses[0].json()
    assert all(response.json() == body for response in responses)
    payment = (await db_session.scalars(select(Payment))).one()
    assert str(payment.id) == body["id"]
    assert payment.idempotency_key == "concurrent-payment"
    assert payment.status == PaymentStatus.PENDING
    assert payment.tariff_id == tariff_id
    assert payment.email == payload["email"]
    assert payment.method == PaymentMethod.CARD
    assert payment.amount == 1_990_000
    assert payment.discount == 0


async def test_concurrent_webhooks_with_conflicting_statuses(
    client: AsyncClient,
    db_session: AsyncSession,
    tariff_id: int,
    webhook_secret: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = Payment(
        tariff_id=tariff_id,
        email="customer@example.com",
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        amount=1_990_000,
        discount=0,
    )
    db_session.add(payment)
    await db_session.commit()

    barrier = asyncio.Barrier(2)
    get_for_update = payment_repository.get_for_update

    async def synchronized_lock(
        session: AsyncSession, payment_id: UUID,
    ) -> Payment | None:
        await session.connection()
        await barrier.wait()
        return await get_for_update(session, payment_id)

    monkeypatch.setattr(
        payment_repository, "get_for_update", synchronized_lock,
    )
    targets = (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED)
    requests = []
    for target in targets:
        body = json.dumps({
            "payment_id": str(payment.id), "status": target.value,
        }).encode()
        signature = hmac.new(
            webhook_secret.encode(), body, hashlib.sha256,
        ).hexdigest()
        requests.append(client.post(
            "/api/v1/webhooks/bank",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
            },
        ))
    responses = await concurrent_requests(*requests)

    assert sorted(response.status_code for response in responses) == [
        status.HTTP_200_OK, status.HTTP_409_CONFLICT,
    ]
    await db_session.refresh(payment)
    for target, response in zip(targets, responses, strict=True):
        if response.status_code == status.HTTP_200_OK:
            assert response.json() == {"result": "ok"}
            assert payment.status == target
        else:
            assert response.json() == {"error": "invalid_transition"}
            assert payment.status != target
