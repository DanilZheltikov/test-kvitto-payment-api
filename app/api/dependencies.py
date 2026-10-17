from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.services.webhook_signature import verify_signature


SessionDep = Annotated[AsyncSession, Depends(get_session)]

IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1),
]


async def verify_bank_signature(
    request: Request,
    signature: Annotated[str | None, Header(alias="X-Signature")] = None,
) -> None:
    secret = settings.webhook_secret.get_secret_value()
    verify_signature(await request.body(), signature, secret)
