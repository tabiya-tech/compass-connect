"""
The integration API: another platform creates its users in Compass with an API key, and sends them into Compass
through a hand-off link that logs them in.
"""

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from firebase_admin import auth

from app.metrics.services.service import IMetricsService
from app.integration.firebase import IntegrationFirebase
from app.integration.repository import ExternalUserRepository, DuplicateExternalUserError
from app.integration.types import CreateExternalUserRequest, CreateExternalUserResponse, HandoffAction, \
    HandoffLink, HandoffLinkResponse, ExternalUserConflict, ExternalUserResponse, ExternalUser, \
    HandoffExchangeResponse
from app.users.new_user_preferences import create_new_user_preferences
from app.users.repositories import IUserPreferenceRepository, UserPreferenceRepositoryError
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from common_libs.time_utilities import get_now, truncate_microseconds

HANDOFF_PATH = "/#/handoff"


class ExternalUserConflictError(Exception):
    def __init__(self, conflict: ExternalUserConflict):
        super().__init__(conflict.value)
        self.conflict = conflict


class InvalidHandoffLinkError(Exception):
    """
    The link is unknown, expired or replaced, or its account can no longer use it. One error for all, on purpose.
    """


def hash_link_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_plain_jobseeker(user: auth.UserRecord) -> bool:
    """
    Custom claims (e.g. the admin `role`) are on the user record and end up in every ID token of the user, whatever
    the sign-in method. A hand-off link must never open such an account, so any claim makes it ineligible.
    """
    return not user.custom_claims and not user.disabled


class IntegrationService:
    def __init__(self, *,
                 user_repository: ExternalUserRepository,
                 user_preferences_repository: IUserPreferenceRepository,
                 metrics_service: IMetricsService,
                 firebase: IntegrationFirebase,
                 link_ttl_minutes: int,
                 frontend_url: str,
                 default_language: str):
        self._users = user_repository
        self._user_preferences = user_preferences_repository
        self._metrics_service = metrics_service
        self._firebase = firebase
        self._link_ttl_minutes = link_ttl_minutes
        self._frontend_url = frontend_url
        self._default_language = default_language
        self._logger = logging.getLogger(self.__class__.__name__)

    async def create_user(self, request: CreateExternalUserRequest) -> tuple[bool, CreateExternalUserResponse]:
        """
        Create the user (or find the one created earlier with the same external id and email), its Firebase account
        and its preferences, and issue a hand-off link.

        :return: whether the user was created by this request, and the response
        :raises ExternalUserConflictError: see ExternalUserConflict
        """
        external_user, created = await self._get_or_create_external_user(request)
        user = await self._ensure_firebase_user(external_user)
        if not is_plain_jobseeker(user):
            self._logger.warning("Refused an external user: the account %s has custom claims or is disabled",
                                 user.uid)
            raise ExternalUserConflictError(ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE)
        await self._ensure_preferences(user.uid)
        link = await self._issue_link(external_user.external_id, request.action)

        return created, CreateExternalUserResponse(
            result="User created, hand-off link issued." if created
            else "User already existed, new hand-off link issued.",
            user=ExternalUserResponse(external_id=external_user.external_id, email=external_user.email,
                                      created_at=external_user.created_at),
            link=link)

    async def exchange_link(self, token: str) -> HandoffExchangeResponse:
        """
        Exchange a hand-off link token for a Firebase custom token. The link stays valid until it expires or is
        replaced by a newer one, so the user can open it again (reload, another device, the same button).

        :raises InvalidHandoffLinkError: for any link that cannot be used
        """
        external_user = await self._users.find_by_valid_link(hash_link_token(token), get_now())
        if external_user is None or external_user.user_id is None:
            raise InvalidHandoffLinkError()

        # check the account again: it may have changed since the link was issued
        user = await asyncio.to_thread(self._firebase.get_user, external_user.user_id)
        if user is None or not is_plain_jobseeker(user):
            self._logger.warning("Refused a hand-off link: the account %s is gone, has custom claims or is disabled",
                                 external_user.user_id)
            raise InvalidHandoffLinkError()

        custom_token = await asyncio.to_thread(self._firebase.create_custom_token, user.uid)
        return HandoffExchangeResponse(custom_token=custom_token, action=external_user.link.action)

    async def _get_or_create_external_user(self, request: CreateExternalUserRequest) -> tuple[ExternalUser, bool]:
        existing = await self._users.find_by_external_id(request.external_id)
        if existing is not None:
            if existing.email != request.email:
                raise ExternalUserConflictError(ExternalUserConflict.EXTERNAL_ID_BOUND_TO_OTHER_EMAIL)
            return existing, False

        if await self._users.find_by_email(request.email) is not None:
            raise ExternalUserConflictError(ExternalUserConflict.EMAIL_BOUND_TO_OTHER_EXTERNAL_ID)

        # an account the API did not create (signed up by themselves, created manually, an admin) is not taken over
        if await asyncio.to_thread(self._firebase.get_user_by_email, request.email) is not None:
            raise ExternalUserConflictError(ExternalUserConflict.ACCOUNT_ALREADY_EXISTS)

        # record first, the Firebase account second: a retry after a failure in between finds this record and
        # finishes it, instead of seeing an account the API did not create
        # MongoDB keeps milliseconds: the response of this request and of later ones show the same created_at
        now = truncate_microseconds(get_now())
        external_user = ExternalUser(external_id=request.external_id, email=request.email,
                                     created_at=now, updated_at=now)
        try:
            await self._users.insert(external_user)
            return external_user, True
        except DuplicateExternalUserError:
            # a concurrent request with the same external id or email was faster
            existing = await self._users.find_by_external_id(request.external_id)
            if existing is not None and existing.email == request.email:
                return existing, False
            raise ExternalUserConflictError(ExternalUserConflict.EXTERNAL_ID_BOUND_TO_OTHER_EMAIL if existing
                                            else ExternalUserConflict.EMAIL_BOUND_TO_OTHER_EXTERNAL_ID)

    async def _ensure_firebase_user(self, external_user: ExternalUser) -> auth.UserRecord:
        if external_user.user_id is not None:
            user = await asyncio.to_thread(self._firebase.get_user, external_user.user_id)
            if user is None:
                # the account was deleted in Firebase after the user was created
                self._logger.warning("The Firebase account %s of an external user no longer exists",
                                     external_user.user_id)
                raise ExternalUserConflictError(ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE)
            return user

        # a new user, or one left half-finished by an earlier request: an account found here was created for this
        # user (accounts created by other means were refused before the record existed)
        user = await asyncio.to_thread(self._firebase.get_user_by_email, external_user.email)
        if user is None:
            user = await asyncio.to_thread(self._firebase.create_user, external_user.email)
        await self._users.set_user_id(external_user.external_id, user.uid, get_now())
        return user

    async def _ensure_preferences(self, user_id: str) -> None:
        if await self._user_preferences.get_user_preference_by_user_id(user_id) is not None:
            return
        try:
            # consent (accepted_tc) is left empty: the user accepts the terms in the frontend, like everyone
            await create_new_user_preferences(
                repository=self._user_preferences,
                metrics_service=self._metrics_service,
                user_id=user_id,
                language=self._default_language,
                invitation_code=None,
                client_id=str(uuid.uuid4()),
                sensitive_personal_data_requirement=SensitivePersonalDataRequirement.NOT_AVAILABLE,
            )
        except UserPreferenceRepositoryError:
            # a concurrent request for the same user created them first
            if await self._user_preferences.get_user_preference_by_user_id(user_id) is None:
                raise

    async def _issue_link(self, external_id: str, action: HandoffAction) -> HandoffLinkResponse:
        now = get_now()
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(minutes=self._link_ttl_minutes)
        # one live link per user: the new link replaces the old one, so a leaked older link stops working
        await self._users.set_link(external_id, HandoffLink(token_hash=hash_link_token(token), action=action,
                                                            expires_at=expires_at), now)
        return HandoffLinkResponse(url=f"{self._frontend_url}{HANDOFF_PATH}?token={token}",
                                   expires_at=expires_at)
