#!/usr/bin/env python3
"""
BARROW.AI — Hybrid database migration script.

Strategy (Option 3):
  1. Check if the Alembic version table exists (= DB has been migrated before).
  2. Fresh DB  → create_all() then stamp head  (bypasses migration files).
  3. Existing DB → alembic upgrade head         (applies only NEW migrations).

This guarantees idempotency on every Jenkins deployment:
  - First deploy  : tables created instantly from ORM models.
  - Later deploys : only incremental schema changes applied.

Usage:
    python scripts/db_migrate.py [--dry-run]
"""

import asyncio
import sys
import subprocess
import argparse
from pathlib import Path

# Make the project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.core.logging import get_logger

# Import every model so that Base.metadata is fully populated
from app.models.domain import (  # noqa: F401
    AdminUser,
    AuditLog,
    Conversation,
    ConversationSource,
    KnowledgeDocument,
    Session,
)

logger = get_logger("db_migrate")

# ── helpers ───────────────────────────────────────────────────────────────────

async def _alembic_version_table_exists() -> bool:
    """Return True if Alembic has already been run against this DB."""
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_schema = 'public'"
                    "    AND table_name   = 'alembic_version'"
                    ")"
                )
            )
            return bool(result.scalar())
    finally:
        await engine.dispose()


async def _create_all_tables(dry_run: bool = False) -> None:
    """Create every table defined in Base.metadata."""
    if dry_run:
        logger.info("dry_run: would call Base.metadata.create_all()")
        return

    engine = create_async_engine(settings.database_url, echo=True)
    try:
        async with engine.begin() as conn:
            # checkfirst=True → no error if tables already exist
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, checkfirst=True
                )
            )
        logger.info("create_all_completed")
    finally:
        await engine.dispose()


def _run_alembic(cmd: list[str], dry_run: bool = False) -> None:
    """Run an alembic sub-command synchronously."""
    full_cmd = ["alembic", "-c", str(ROOT / "alembic" / "alembic.ini")] + cmd
    logger.info("running_alembic", cmd=" ".join(full_cmd))
    if dry_run:
        logger.info("dry_run: skipping alembic call")
        return
    result = subprocess.run(full_cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"Alembic command failed: {' '.join(cmd)}")


# ── main logic ────────────────────────────────────────────────────────────────

async def migrate(dry_run: bool = False) -> None:
    logger.info("db_migrate_start", dry_run=dry_run)

    alembic_exists = await _alembic_version_table_exists()

    if not alembic_exists:
        # ── Fresh DB (first deployment) ───────────────────────────────────────
        logger.info("fresh_db_detected", strategy="create_all + stamp head")

        # 1. Create all tables directly from ORM models
        await _create_all_tables(dry_run=dry_run)

        # 2. Tell Alembic the schema is already at HEAD so it won't re-run
        #    any existing migration files on the next deployment.
        _run_alembic(["stamp", "head"], dry_run=dry_run)

        logger.info(
            "fresh_db_ready",
            message="Tables created via create_all(); Alembic stamped at HEAD",
        )

    else:
        # ── Existing DB (subsequent deployments) ─────────────────────────────
        logger.info("existing_db_detected", strategy="alembic upgrade head")

        # Only apply migrations that haven't been applied yet.
        _run_alembic(["upgrade", "head"], dry_run=dry_run)

        logger.info("migrations_applied")

    logger.info("db_migrate_done")


def main() -> None:
    parser = argparse.ArgumentParser(description="BARROW.AI hybrid DB migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
