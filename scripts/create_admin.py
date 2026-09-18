#!/usr/bin/env python3
"""
Create initial admin user for BARROW.AI.
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import get_session_context
from app.repositories.admin_repository import AdminRepository
from app.models.domain.admin import AdminRole
from app.core.logging import get_logger

logger = get_logger(__name__)


async def create_admin(email: str, full_name: str, role: str, password: str = None):
    import os
    import secrets

    generated = False
    if not password:
        password = os.getenv("ADMIN_INITIAL_PASSWORD") or os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
    
    if not password:
        password = secrets.token_urlsafe(20)
        generated = True
    
    async with get_session_context() as session:
        repo = AdminRepository(session)
        
        existing = await repo.get_by_email(email)
        if existing:
            logger.info(f"Admin {email} already exists")
            print(f"Admin {email} already exists")
            return
        
        admin = await repo.create_admin(
            email=email,
            password=password,
            full_name=full_name,
            role=AdminRole(role),
        )
        
        await session.commit()
        
        logger.info(f"Admin created: {admin.email}")
        if generated and not os.getenv("CI"):
            print(f"Admin created: {email} (generated bootstrap password: {password})")
        else:
            print(f"Admin created: {email}")


def main():
    parser = argparse.ArgumentParser(description="Create BARROW.AI admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="superadmin", choices=["superadmin", "admin", "auditor", "viewer"])
    parser.add_argument("--password", help="Password (generated if not provided)")
    args = parser.parse_args()
    asyncio.run(create_admin(args.email, args.name, args.role, args.password))


if __name__ == "__main__":
    main()