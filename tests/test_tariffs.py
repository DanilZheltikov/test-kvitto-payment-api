from fastapi import status
from httpx import AsyncClient


async def test_get_tariffs(client: AsyncClient) -> None:
    response = await client.get("/api/v1/tariffs")

    assert response.status_code == status.HTTP_200_OK
    tariffs = response.json()
    assert isinstance(tariffs, list)
    assert len(tariffs) == 3

    for tariff in tariffs:
        assert set(tariff) == {"id", "title", "price"}
        assert type(tariff["id"]) is int
        assert tariff["id"] > 0
        assert type(tariff["price"]) is int

    assert len({tariff["id"] for tariff in tariffs}) == len(tariffs)
    assert {tariff["title"]: tariff["price"] for tariff in tariffs} == {
        "basic": 990_000,
        "standard": 1_990_000,
        "premium": 2_990_000,
    }
