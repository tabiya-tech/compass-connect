"""
Shared utilities for resolving user_id sets by filter dimension (institution, province, sector).
Used by analytics route handlers to scope aggregations to a filtered population.
"""
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.server_dependencies.database_collections import Collections
from app.teveta.loader import get_data, SECTOR_KEY_MAP


async def resolve_user_ids_for_institution(institution_name: str, userdata_db: AsyncIOMotorDatabase) -> list[str]:
    docs = await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).find(
        {"data.institution_name": institution_name}, {"user_id": 1}
    ).to_list(length=None)
    return [d["user_id"] for d in docs if d.get("user_id")]


async def resolve_user_ids_for_province(province: str, userdata_db: AsyncIOMotorDatabase) -> list[str]:
    docs = await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).find(
        {"data.province": province}, {"user_id": 1}
    ).to_list(length=None)
    return [d["user_id"] for d in docs if d.get("user_id")]


async def resolve_user_ids_for_sector(sector: str, userdata_db: AsyncIOMotorDatabase) -> list[str]:
    """
    Resolve user_ids whose enrolled programme belongs to the given sector.

    Uses the in-memory TEVETA data (loaded at startup) to find programme names
    that have priority_sectors[<teveta_key>] == True, then matches those names
    against PLAIN_PERSONAL_DATA.data.programme_name.

    sector must be one of the hub display names: Agriculture, Energy, Hospitality, Mining, Water.
    SECTOR_KEY_MAP translates these to the TEVETA internal keys used in priority_sectors.
    """
    teveta_key = SECTOR_KEY_MAP.get(sector)
    if not teveta_key:
        return []
    programme_names = {
        p["name"]
        for p in get_data().get("programmes", [])
        if p.get("priority_sectors", {}).get(teveta_key)
    }
    if not programme_names:
        return []
    ppd_docs = await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).find(
        {"data.programme_name": {"$in": list(programme_names)}}, {"user_id": 1}
    ).to_list(length=None)
    return [d["user_id"] for d in ppd_docs if d.get("user_id")]


def intersect_user_id_sets(sets: list[list[str]]) -> Optional[list[str]]:
    """
    Intersect multiple user_id lists. Returns None when no filters are active
    (meaning: all users). Returns an empty list when filters yield no overlap.
    """
    if not sets:
        return None
    result: set[str] = set(sets[0])
    for s in sets[1:]:
        result &= set(s)
    return list(result)
