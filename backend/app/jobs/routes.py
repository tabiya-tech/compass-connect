from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from app.analytics.types import PaginatedListResponse
from app.constants.errors import HTTPErrorResponse
from app.jobs.get_job_service import get_job_service
from app.jobs.service import IJobService, JobDocument, JobStats, MatchedJobDocument
from app.users.auth import Authentication, UserInfo
from app.user_profile.repository import UserProfileRepository
from app.job_preferences.get_job_preferences_service import get_job_preferences_service
from app.job_preferences.service import IJobPreferencesService
from app.agent.recommender_advisor_agent.matching_service_client import MatchingServiceClient, MatchingServiceError
from app.app_config import get_application_config
from app.programme_skills.repository import ProgrammeSkillsRepository
from app.server_dependencies.database_collections import Collections
from app.server_dependencies.db_dependencies import CompassDBProvider
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


def add_jobs_routes(app: FastAPI, authentication: Optional[Authentication] = None):
    """
    Add all routes related to jobs to the FastAPI app.
    :param app: FastAPI: The FastAPI app to add the routes to.
    """
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.get(
        "/stats",
        response_model=JobStats,
        responses={HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse}},
        description="Get aggregate stats for jobs: total count, distinct sectors, distinct source platforms.",
    )
    async def get_job_stats(
        response: Response,
        job_service: IJobService = Depends(get_job_service),
    ):
        response.headers["Access-Control-Allow-Origin"] = "*"
        try:
            return await job_service.get_job_stats()
        except Exception as exc:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to fetch job stats",
            ) from exc

    @router.get(
        "",
        response_model=PaginatedListResponse[JobDocument],
        responses={
            HTTPStatus.BAD_REQUEST: {"model": HTTPErrorResponse},
            HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
        },
        description="List jobs with optional filters and cursor-based pagination.",
    )
    async def list_jobs(
        response: Response,
        category: Optional[str] = Query(default=None, description="Filter by job category"),
        employment_type: Optional[str] = Query(default=None, description="Filter by employment type"),
        location: Optional[str] = Query(default=None, description="Filter by job location"),
        days: Optional[int] = Query(default=None, ge=1, le=3650, description="Only include jobs posted within the last N days"),
        cursor: Optional[str] = Query(default=None, description="Pagination cursor from previous response"),
        limit: Annotated[int, Query(ge=1, le=100, description="Max items per page")] = 20,
        include: Optional[str] = Query(default=None, description="Comma-separated: 'count' to include total"),
        job_service: IJobService = Depends(get_job_service),
    ):
        """
        List jobs stored in MongoDB.

        Optional query parameters filter by category, employment type, location,
        and/or posted_date window. Pagination is controlled by `cursor` and `limit`.
        """
        response.headers["Access-Control-Allow-Origin"] = "*"
        try:
            return await job_service.list_jobs(
                category=category,
                employment_type=employment_type,
                location=location,
                days=days,
                cursor=cursor,
                limit=limit,
                include=include,
            )
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to fetch jobs from MongoDB",
            ) from exc

    if authentication is not None:
        _lock = asyncio.Lock()
        _matching_client: Optional[MatchingServiceClient] = None
        _matching_client_initialized = False

        async def _get_matching_client() -> Optional[MatchingServiceClient]:
            nonlocal _matching_client, _matching_client_initialized
            if not _matching_client_initialized:
                async with _lock:
                    if not _matching_client_initialized:
                        try:
                            config = get_application_config()
                            if config.matching_service_url and config.matching_service_api_key:
                                _matching_client = MatchingServiceClient(
                                    base_url=config.matching_service_url,
                                    api_key=config.matching_service_api_key,
                                )
                        except Exception as exc:
                            logger.warning("Could not initialise matching service client: %s", exc)
                        _matching_client_initialized = True
            return _matching_client

        @router.get(
            "/matched",
            response_model=List[MatchedJobDocument],
            responses={
                HTTPStatus.UNAUTHORIZED: {"model": HTTPErrorResponse},
                HTTPStatus.INTERNAL_SERVER_ERROR: {"model": HTTPErrorResponse},
            },
            description=(
                "Return jobs personalised for the authenticated user based on their skills and "
                "preferences, using the external matching service."
            ),
        )
        async def get_matched_jobs(
            user_info: UserInfo = Depends(authentication.get_user_info()),
            job_preferences_service: IJobPreferencesService = Depends(get_job_preferences_service),
            job_service: IJobService = Depends(get_job_service),
            application_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_application_db),
            userdata_db: AsyncIOMotorDatabase = Depends(CompassDBProvider.get_userdata_db),
            limit: Annotated[int, Query(ge=1, le=100, description="Max results")] = 20,
        ):
            try:
                matching_client = await _get_matching_client()
                if matching_client is None:
                    logger.warning("Matching service not configured; returning empty list")
                    return []

                user_profile_repo = UserProfileRepository(application_db, userdata_db)

                # Fetch session id and personal data in parallel
                session_id, personal_data = await asyncio.gather(
                    user_profile_repo.get_latest_session_id(user_info.user_id),
                    user_profile_repo.get_personal_data(user_info.user_id),
                )

                province: Optional[str] = None
                programme_name: Optional[str] = None
                if personal_data:
                    province = personal_data.get("province")
                    programme_name = personal_data.get("programme_name")

                # Build skills vector from the programme_skills collection
                skills_vector: dict = {"skills": []}
                if programme_name:
                    programme_skills_repo = ProgrammeSkillsRepository(
                        application_db.get_collection(Collections.PROGRAMME_SKILLS)
                    )
                    programme_skills_doc = await programme_skills_repo.find_by_programme_name(programme_name)
                    if programme_skills_doc:
                        skills_vector = {
                            "skills": [
                                {
                                    "skill_id": skill.UUID,
                                    "uuid": skill.UUID,
                                    "originUUID": skill.originUUID,
                                    "preferred_label": skill.preferredLabel,
                                    "skill_type": skill.skillType,
                                    "proficiency": 0.8,
                                    "score": 0.8,
                                }
                                for skill in programme_skills_doc.skills
                            ]
                        }

                # Build preference vector from job preferences
                preference_vector = None
                if session_id is not None:
                    prefs = await job_preferences_service.get_by_session(session_id)
                    if prefs:
                        preference_vector = {
                            "earnings_per_month": prefs.financial_importance,
                            "task_content": prefs.task_preference_importance,
                            "physical_demand": 0.5,
                            "work_flexibility": prefs.work_life_balance_importance,
                            "social_interaction": 0.5,
                            "career_growth": prefs.career_advancement_importance,
                            "social_meaning": prefs.social_impact_importance,
                        }

                logger.info(
                    "Calling matching service for user %s (skills=%d, programme=%s, has_prefs=%s)",
                    user_info.user_id, len(skills_vector["skills"]), programme_name, preference_vector is not None,
                )

                raw = await matching_client.generate_recommendations(
                    youth_id=user_info.user_id,
                    city=None,
                    province=str(province) if province else None,
                    skills_vector=skills_vector,
                    preference_vector=preference_vector,
                )

                # Response is a list; take the first user's results
                user_data = raw[0] if isinstance(raw, list) and raw else (raw or {})
                opportunity_recs = user_data.get("opportunity_recommendations", [])[:limit]

                # Enrich matched jobs with employer, category, posted_date from the jobs collection
                matched_uuids = [opp.get("uuid") for opp in opportunity_recs if opp.get("uuid")]
                jobs_by_uuid = await job_service.get_jobs_by_uuids(matched_uuids)

                results = []
                for opp in opportunity_recs:
                    doc = MatchedJobDocument.model_validate(opp)
                    job = jobs_by_uuid.get(doc.uuid or "")
                    if job:
                        doc.employer = job.employer
                        doc.category = job.category
                        doc.posted_date = job.posted_date
                    results.append(doc)

                logger.info("Matching service returned %d opportunities for user %s", len(results), user_info.user_id)
                return results

            except MatchingServiceError as exc:
                logger.error("Matching service error for user %s: %s", user_info.user_id, exc)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail="Matching service unavailable",
                ) from exc
            except Exception as exc:
                logger.exception("Error in get_matched_jobs for user %s", user_info.user_id)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch matched jobs",
                ) from exc

    app.include_router(router)
