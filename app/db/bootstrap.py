"""Idempotent database initialization for the Docker deployment."""

import os
from pathlib import Path

import bcrypt
from sqlalchemy import text
from sqlalchemy.engine import Engine


def initialize_database(engine: Engine) -> None:
    migration_path = Path(__file__).resolve().parents[2] / "migrations" / "002_operational_workflows.sql"
    migration = migration_path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in migration.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)

        admin_username = os.environ.get("APP_ADMIN_USERNAME", "").strip()
        admin_password = os.environ.get("APP_ADMIN_PASSWORD", "")
        if not admin_username or not admin_password:
            raise RuntimeError(
                "APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD must be configured."
            )
        if len(admin_password.encode("utf-8")) > 72:
            raise RuntimeError("APP_ADMIN_PASSWORD must not exceed 72 UTF-8 bytes.")

        existing_admin = connection.execute(
            text("SELECT id FROM app_users WHERE username = :username"),
            {"username": admin_username},
        ).scalar_one_or_none()
        if existing_admin is None:
            password_hash = bcrypt.hashpw(
                admin_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("ascii")
            connection.execute(
                text(
                    """
                    INSERT INTO app_users (username, password_hash, role)
                    VALUES (:username, :password_hash, 'admin')
                    """
                ),
                {"username": admin_username, "password_hash": password_hash},
            )

        sources = (
            ("population", "Population / demographic", "population"),
            ("marketplace", "Marketplace transactions", "marketplace"),
            ("system_log", "System logs", "system_log"),
        )
        for code, name, source_type in sources:
            connection.execute(
                text(
                    """
                    INSERT INTO source_registry
                        (source_code, source_name, source_type, authorized_purpose)
                    VALUES (:code, :name, :source_type, :purpose)
                    ON CONFLICT (source_code) DO NOTHING
                    """
                ),
                {
                    "code": code,
                    "name": name,
                    "source_type": source_type,
                    "purpose": "Authorized local MVP testing using synthetic data.",
                },
            )
        connection.execute(
            text(
                """
                INSERT INTO correlation_rules
                    (rule_code, rule_name, rule_version, rule_definition)
                VALUES
                    ('TX_EVENT_300S', 'Transaction to system event within 300 seconds',
                     1, CAST(:definition AS jsonb))
                ON CONFLICT (rule_code) DO NOTHING
                """
            ),
            {
                "definition": (
                    '{"join_field":"authorized_join_ref",'
                    '"time_window_seconds":300,'
                    '"left_table":"marketplace_transactions",'
                    '"right_table":"system_events"}'
                )
            },
        )
