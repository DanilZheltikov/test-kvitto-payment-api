import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def webhook_secret() -> str:
    return "test-webhook-secret"


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    """Start PostgreSQL only when an integration fixture is requested."""
    with PostgresContainer(
        "postgres:17",
        username="test",
        password="test",
        dbname="kvitto_test",
        driver="asyncpg",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def database_url(
    postgres: PostgresContainer,
    webhook_secret: str,
) -> Iterator[str]:
    """Apply real migrations before importing the application."""
    project_root = Path(__file__).resolve().parents[1]
    with pytest.MonkeyPatch.context() as patch:
        for name, value in {
            "POSTGRES_DB": postgres.dbname,
            "POSTGRES_USER": postgres.username,
            "POSTGRES_PASSWORD": postgres.password,
            "DB_HOST": postgres.get_container_host_ip(),
            "DB_PORT": str(postgres.get_exposed_port(5432)),
            "WEBHOOK_SECRET": webhook_secret,
        }.items():
            patch.setenv(name, value)

        # Alembic's env.py calls asyncio.run(), so use a separate process.
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(project_root / "alembic.ini"),
                "upgrade",
                "head",
            ],
            cwd=project_root,
            check=True,
        )
        yield postgres.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def db_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(
    db_engine: AsyncEngine
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def app(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    webhook_secret: str,
) -> AsyncIterator[FastAPI]:
    from app import main
    from app.db.session import get_session

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    with pytest.MonkeyPatch.context() as patch:
        # Lifespan uses these globals directly, bypassing Depends(get_session).
        patch.setattr(main, "engine", db_engine)
        patch.setattr(main, "session_factory", session_factory)
        patch.setattr(
            main.settings,
            "webhook_secret",
            SecretStr(webhook_secret)
        )
        patch.setattr(
            main.app,
            "dependency_overrides",
            {
                **main.app.dependency_overrides,
                get_session: override_get_session
            },
        )
        async with LifespanManager(main.app):
            yield main.app


@pytest_asyncio.fixture
async def clean_database(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reset committed data; each request keeps its own transaction."""
    from app.services.tariffs import tariff_service

    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("TRUNCATE TABLE payments, tariffs RESTART IDENTITY")
            )
        await tariff_service.seed(session)


@pytest_asyncio.fixture
async def db_session(
    clean_database: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide a separate session for setup and persisted-state assertions."""
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(
    app: FastAPI,
    clean_database: None
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as http_client:
        yield http_client
