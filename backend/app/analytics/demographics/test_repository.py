"""Tests for the demographics repository (grouped counts from plain_personal_data)."""
from typing import Awaitable

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.analytics.demographics.repository import DemographicsRepository
from app.server_dependencies.database_collections import Collections


@pytest.fixture(scope="function")
async def populated_repository(
    in_memory_userdata_database: Awaitable[AsyncIOMotorDatabase],
) -> DemographicsRepository:
    """
    Data layout:
      - user-a, user-b at "Test School": female/Lusaka, male/Lusaka
      - user-c at "Another School": female/Copperbelt
      - user-d at "Test School": gender missing (excluded from the gender breakdown)
    """
    userdata_db = await in_memory_userdata_database
    await userdata_db.get_collection(Collections.PLAIN_PERSONAL_DATA).insert_many([
        {"user_id": "user-a", "data": {"institution_name": "Test School", "gender": "female", "province": "Lusaka"}},
        {"user_id": "user-b", "data": {"institution_name": "Test School", "gender": "male", "province": "Lusaka"}},
        {"user_id": "user-c", "data": {"institution_name": "Other School", "gender": "female", "province": "Copperbelt"}},
        {"user_id": "user-d", "data": {"institution_name": "Test School", "province": "Lusaka"}},
    ])
    return DemographicsRepository(userdata_db)


class TestGetDemographics:
    @pytest.mark.asyncio
    async def test_returns_gender_and_region_charts(self, populated_repository: Awaitable[DemographicsRepository]):
        repo = await populated_repository
        result = await repo.get_demographics()

        assert result[0]["type"] == "pie-chart"
        assert result[0]["name"] == "gender"
        assert {item["name"]: item["value"] for item in result[0]["items"]} == {"female": 2, "male": 1}

        assert result[1]["type"] == "horizontal-bar-chart"
        assert result[1]["name"] == "region"
        assert {item["name"]: item["value"] for item in result[1]["items"]} == {"Lusaka": 3, "Copperbelt": 1}

    @pytest.mark.asyncio
    async def test_excludes_users_missing_the_field(self, populated_repository: Awaitable[DemographicsRepository]):
        repo = await populated_repository
        result = await repo.get_demographics()

        gender_total = sum(item["value"] for item in result[0]["items"])
        assert gender_total == 3  # user-d has no gender recorded

    @pytest.mark.asyncio
    async def test_institution_scope_limits_counts(self, populated_repository: Awaitable[DemographicsRepository]):
        repo = await populated_repository
        result = await repo.get_demographics(institution_names=["Test School"])

        assert {item["name"]: item["value"] for item in result[0]["items"]} == {"female": 1, "male": 1}
        assert {item["name"]: item["value"] for item in result[1]["items"]} == {"Lusaka": 3}
