#!/usr/bin/env python3
"""
Seed / cleanup test data for Skills Analytics filter verification.

Seeds 6 users spanning all 5 sectors (Agriculture, Energy, Hospitality, Mining, Water)
and 4 provinces (Lusaka, Copperbelt, Northern, Central) so that province and sector
filters can be tested end-to-end in the admin dashboard.

All test documents share the prefix '_test_analytics_' so cleanup is safe and surgical.

Usage (from backend/):
    poetry run python scripts/seed_analytics_test_data.py            # seed
    poetry run python scripts/seed_analytics_test_data.py --cleanup  # remove

Reads APPLICATION_MONGODB_URI, APPLICATION_DATABASE_NAME,
       USERDATA_MONGODB_URI, USERDATA_DATABASE_NAME from .env or environment.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing app modules from the backend root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from app.server_dependencies.database_collections import Collections
from app.teveta.loader import SECTOR_KEY_MAP, get_data

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TEST_PREFIX = "_test_analytics_"

# (user_id_suffix, province, sector_hub_name)
# Two Agriculture users across different provinces lets us verify the
# province+sector intersection test case.
TEST_USERS = [
    ("001", "Lusaka",     "Agriculture"),
    ("002", "Copperbelt", "Energy"),
    ("003", "Northern",   "Mining"),
    ("004", "Lusaka",     "Hospitality"),
    ("005", "Central",    "Water"),
    ("006", "Copperbelt", "Agriculture"),   # second Agriculture, different province
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pick_programme_for_sector(sector_hub_name: str) -> str:
    """Return a programme name from TEVETA data that belongs to the given sector."""
    teveta_key = SECTOR_KEY_MAP[sector_hub_name]
    for p in get_data().get("programmes", []):
        if p.get("priority_sectors", {}).get(teveta_key):
            return p["name"]
    raise ValueError(f"No programme found in TEVETA data for sector {sector_hub_name!r}")


def _build_docs(user_id: str, province: str, sector_hub_name: str) -> tuple:
    programme_name = _pick_programme_for_sector(sector_hub_name)
    session_id = f"{user_id}_session"

    plain_personal_data = {
        "user_id": user_id,
        "created_at": _now(),
        "updated_at": _now(),
        "data": {
            "first_name": "Test",
            "last_name": f"User{user_id[-3:]}",
            "institution_name": "Test Institution",
            "programme_name": programme_name,
            "province": province,
            "school_year": "Year 1",
        },
    }

    user_preferences = {
        "user_id": user_id,
        "sessions": [session_id],
        "accepted_tc": _now(),
    }

    skill_gap_recommendations = {
        "user_id": user_id,
        "skill_gap_recommendations": [
            {
                "skill_id": f"skill_{sector_hub_name.lower()}_001",
                "skill_label": f"{sector_hub_name} Planning",
                "job_unlock_count": 3,
                "proximity_score": 0.82,
            },
            {
                "skill_id": f"skill_{sector_hub_name.lower()}_002",
                "skill_label": f"{sector_hub_name} Management",
                "job_unlock_count": 5,
                "proximity_score": 0.75,
            },
        ],
    }

    skills_supply_state = {
        "session_id": session_id,
        "conversation_phase": "DIVE_IN",
        "experiences_state": {
            "exp_001": {
                "dive_in_phase": "PROCESSED",
                "experience": {
                    "top_skills": [
                        {
                            "UUID": f"skill-uuid-{sector_hub_name.lower()}-a",
                            "preferredLabel": f"{sector_hub_name} Operations",
                            "score": 0.88,
                        },
                        {
                            "UUID": f"skill-uuid-{sector_hub_name.lower()}-b",
                            "preferredLabel": f"{sector_hub_name} Analysis",
                            "score": 0.72,
                        },
                    ]
                },
            }
        },
    }

    return plain_personal_data, user_preferences, skill_gap_recommendations, skills_supply_state


def _connect():
    app_uri = os.environ.get("APPLICATION_MONGODB_URI", "")
    app_db_name = os.environ.get("APPLICATION_DATABASE_NAME", "")
    userdata_uri = os.environ.get("USERDATA_MONGODB_URI", "")
    userdata_db_name = os.environ.get("USERDATA_DATABASE_NAME", "")

    if not all([app_uri, app_db_name, userdata_uri, userdata_db_name]):
        raise SystemExit(
            "Missing required env vars. Ensure APPLICATION_MONGODB_URI, "
            "APPLICATION_DATABASE_NAME, USERDATA_MONGODB_URI, and "
            "USERDATA_DATABASE_NAME are set (or present in backend/.env)."
        )

    app_client = AsyncIOMotorClient(app_uri, tlsAllowInvalidCertificates=True)
    userdata_client = AsyncIOMotorClient(userdata_uri, tlsAllowInvalidCertificates=True)
    return app_client[app_db_name], userdata_client[userdata_db_name], app_client, userdata_client


async def seed():
    app_db, userdata_db, app_client, userdata_client = _connect()
    try:
        logger.info("Seeding %d test users (prefix=%r)...", len(TEST_USERS), TEST_PREFIX)
        for suffix, province, sector in TEST_USERS:
            user_id = f"{TEST_PREFIX}{suffix}"
            ppd, prefs, gap, supply = _build_docs(user_id, province, sector)
            logger.info(
                "  %-30s province=%-12s sector=%-12s programme=%s",
                user_id, province, sector, ppd["data"]["programme_name"],
            )

            await userdata_db[Collections.PLAIN_PERSONAL_DATA].replace_one(
                {"user_id": user_id}, ppd, upsert=True
            )
            await app_db[Collections.USER_PREFERENCES].replace_one(
                {"user_id": user_id}, prefs, upsert=True
            )
            await app_db[Collections.USER_RECOMMENDATIONS].replace_one(
                {"user_id": user_id}, gap, upsert=True
            )
            await app_db[Collections.EXPLORE_EXPERIENCES_DIRECTOR_STATE].replace_one(
                {"session_id": supply["session_id"]}, supply, upsert=True
            )

        logger.info("")
        logger.info("Seed complete. Expected filter results:")
        logger.info("  All filters off              → 6 users in both charts")
        logger.info("  Province = Lusaka            → 2 users (Agriculture + Hospitality)")
        logger.info("  Province = Copperbelt        → 2 users (Energy + Agriculture)")
        logger.info("  Sector = Agriculture         → 2 users (Lusaka + Copperbelt)")
        logger.info("  Sector = Energy              → 1 user  (Copperbelt)")
        logger.info("  Sector = Hospitality         → 1 user  (Lusaka)")
        logger.info("  Sector = Mining              → 1 user  (Northern)")
        logger.info("  Sector = Water               → 1 user  (Central)")
        logger.info("  Province=Copperbelt + Sector=Agriculture → 1 user (intersection)")
        logger.info("  Province=Lusaka    + Sector=Mining       → 0 users (empty state)")
        logger.info("")
        logger.info("Run with --cleanup to remove all test data when done.")
    finally:
        app_client.close()
        userdata_client.close()


async def cleanup():
    app_db, userdata_db, app_client, userdata_client = _connect()
    try:
        logger.info("Removing test data with prefix %r ...", TEST_PREFIX)
        user_ids = [f"{TEST_PREFIX}{suffix}" for suffix, _, _ in TEST_USERS]
        session_ids = [f"{uid}_session" for uid in user_ids]

        r = await userdata_db[Collections.PLAIN_PERSONAL_DATA].delete_many(
            {"user_id": {"$in": user_ids}}
        )
        logger.info("  plain_personal_data:                   %d deleted", r.deleted_count)

        r = await app_db[Collections.USER_PREFERENCES].delete_many(
            {"user_id": {"$in": user_ids}}
        )
        logger.info("  user_preferences:                      %d deleted", r.deleted_count)

        r = await app_db[Collections.USER_RECOMMENDATIONS].delete_many(
            {"user_id": {"$in": user_ids}}
        )
        logger.info("  user_recommendations:                  %d deleted", r.deleted_count)

        r = await app_db[Collections.EXPLORE_EXPERIENCES_DIRECTOR_STATE].delete_many(
            {"session_id": {"$in": session_ids}}
        )
        logger.info("  explore_experiences_director_state:    %d deleted", r.deleted_count)

        logger.info("Cleanup complete.")
    finally:
        app_client.close()
        userdata_client.close()


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        asyncio.run(cleanup())
    else:
        asyncio.run(seed())
