#!/usr/bin/env python3
"""Seed initial data for BARROW.AI."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import get_session_context
from app.repositories.admin_repository import AdminRepository
from app.models.domain.admin import AdminRole


async def seed():
    async with get_session_context() as session:
        repo = AdminRepository(session)
        existing = await repo.get_by_email("admin@pace.gm")
        if not existing:
            await repo.create_admin(
                email="admin@pace.gm",
                password="Admin123!",
                full_name="PACE Administrator",
                role=AdminRole.SUPERADMIN,
            )
            print("Admin user created")
        else:
            print("Admin already exists")


if __name__ == "__main__":
    asyncio.run(seed())