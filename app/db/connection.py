"""PostgreSQL connection configuration shared by the API and dashboard."""

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


def create_database_engine() -> Engine:
    """Create a PostgreSQL engine from Docker Compose environment settings."""
    required_settings = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing_settings = [
        setting for setting in required_settings if not os.environ.get(setting)
    ]
    if missing_settings:
        raise ValueError(
            "Missing PostgreSQL environment settings: "
            + ", ".join(missing_settings)
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
