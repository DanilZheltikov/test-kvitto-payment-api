from fastapi import APIRouter

from app.api.dependencies import SessionDep
from app.models.tariff import Tariff
from app.schemas.tariff import TariffRead
from app.services.tariffs import tariff_service


router = APIRouter(prefix="/tariffs")


@router.get("", response_model=list[TariffRead])
async def list_tariffs(
    session: SessionDep,
) -> list[Tariff]:
    return await tariff_service.list(session)
