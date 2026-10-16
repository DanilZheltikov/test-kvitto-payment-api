from pydantic import BaseModel, ConfigDict

from app.schemas.types import Money


class TariffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    price: Money
