"""
The integration API: another platform creates its users in Compass with an API key, and sends them into Compass
through a hand-off link that logs them in.
"""

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from firebase_admin import auth
from pydantic import BaseModel, Field

from app.agent.agent_director.abstract_agent_director import ConversationPhase
from app.agent.explore_experiences_agent_director import DiveInPhase
from app.application_state import ApplicationStateStore
from app.conversations.experience._types import ExperienceResponse
from app.integration.firebase import IntegrationFirebase
from app.integration.repository import ExternalUserRepository, DuplicateExternalUserError
from app.integration.return_url_validation import validate_return_url, InvalidReturnUrlError
from app.integration.types import CreateExternalUserRequest, CreateExternalUserResponse, HandoffAction, \
    HandoffLink, HandoffLinkResponse, ExternalUserConflict, ExternalUserResponse, ExternalUser, \
    HandoffExchangeResponse, Webhook
from app.users.preferences_service import IUserPreferencesService
from app.users.repositories import IUserPreferenceRepository, UserPreferenceRepositoryError
from app.users.sensitive_personal_data.types import SensitivePersonalDataRequirement
from app.users.types import UserPreferencesRepositoryUpdateRequest
from common_libs.time_utilities import get_now, truncate_microseconds

HANDOFF_PATH = "/#/handoff"


# The results models are here, not in types.py: ExperienceResponse pulls in the agents, and types.py is imported at
# start-up by the database setup (create_integration_indexes), before them.
class ConversationResults(BaseModel):
    session_id: int
    conversation_completed: bool
    conversation_conducted_at: Optional[datetime] = Field(description="The last turn; null when not started.")
    experiences: list[ExperienceResponse] = Field(description="The experiences the user explored, as they see "
                                                              "them (edits included, deleted ones left out).")


class ExternalUserResultsResponse(BaseModel):
    external_id: str
    email: str
    conversations: list[ConversationResults] = Field(description="One per conversation of the user, newest first.")


class ExternalUserConflictError(Exception):
    def __init__(self, conflict: ExternalUserConflict):
        super().__init__(conflict.value)
        self.conflict = conflict


class ExternalUserNotFoundError(Exception):
    """
    No user with this external id, or its Firebase account is not created yet.
    """


class InvalidWebhookError(Exception):
    """
    Webhooks are not enabled on this instance, or the webhook URL is not allowed. The message says which.
    """


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
                 user_preferences_service: IUserPreferencesService,
                 application_state_store: ApplicationStateStore,
                 firebase: IntegrationFirebase,
                 link_ttl_minutes: int,
                 frontend_url: str,
                 default_language: str,
                 return_url_origins: list[str],
                 webhooks_enabled: bool,
                 webhook_url_origins: list[str]):
        self._users = user_repository
        self._user_preferences = user_preferences_repository
        self._user_preferences_service = user_preferences_service
        self._application_state_store = application_state_store
        self._firebase = firebase
        self._link_ttl_minutes = link_ttl_minutes
        self._frontend_url = frontend_url
        self._default_language = default_language
        self._return_url_origins = return_url_origins
        self._webhooks_enabled = webhooks_enabled
        self._webhook_url_origins = webhook_url_origins
        self._logger = logging.getLogger(self.__class__.__name__)

    async def create_user(self, request: CreateExternalUserRequest) -> tuple[bool, CreateExternalUserResponse]:
        """
        Create the user (or find the one created earlier with the same external id and email), its Firebase account
        and its preferences, and issue a hand-off link.

        :return: whether the user was created by this request, and the response
        :raises ExternalUserConflictError: see ExternalUserConflict
        :raises InvalidReturnUrlError: before anything is created
        :raises InvalidWebhookError: before anything is created
        """
        if request.return_url is not None:
            validate_return_url(request.return_url, self._return_url_origins)
        if request.webhook_url is not None:
            self._validate_webhook_url(request.webhook_url)
        external_user, created = await self._get_or_create_external_user(request)
        user = await self._ensure_firebase_user(external_user)
        if not is_plain_jobseeker(user):
            self._logger.warning("Refused an external user: the account %s has custom claims or is disabled",
                                 user.uid)
            raise ExternalUserConflictError(ExternalUserConflict.ACCOUNT_NOT_ELIGIBLE)
        await self._ensure_preferences(user.uid)
        # each call replaces it, and a call without it removes it ("": the update skips None)
        await self._user_preferences.update_user_preference(
            user.uid, UserPreferencesRepositoryUpdateRequest(return_url=request.return_url or ""))
        # like the return URL: each call replaces it, and a call without it removes it
        await self._users.set_webhook(
            external_user.external_id,
            Webhook(url=request.webhook_url, secret=request.webhook_secret) if request.webhook_url else None,
            get_now())
        link = await self._issue_link(external_user.external_id, request.action)

        return created, CreateExternalUserResponse(
            result="User created, hand-off link issued." if created
            else "User already existed, new hand-off link issued.",
            user=ExternalUserResponse(external_id=external_user.external_id, email=external_user.email,
                                      return_url=request.return_url, webhook_url=request.webhook_url,
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

    async def get_results(self, external_id: str) -> ExternalUserResultsResponse:
        """
        What the user's skills conversations produced, newest first like the sessions, so a new conversation does
        not hide a completed one. Only the explored experiences: the deleted ones are not in them, and the ones
        still being explored are left out.

        :raises ExternalUserNotFoundError: for an unknown external id, or one without a Firebase account yet
        """
        external_user = await self._users.find_by_external_id(external_id)
        if external_user is None or external_user.user_id is None:
            raise ExternalUserNotFoundError()

        # the sessions come from the user's own preferences: a session of another user can never be read
        preferences = await self._user_preferences.get_user_preference_by_user_id(external_user.user_id)
        conversations = []
        for session_id in preferences.sessions if preferences else []:
            # the store, not the state manager: the manager saves a new empty state when the store returns None, and
            # the store also returns None when the read fails, so a partner polling this could wipe a conversation
            # TODO: get_state can still save healed or upgraded state, and a failed read is reported here as an
            #  incomplete conversation. Use a read-only load and return a 5xx on failure once the store has one.
            state = await self._application_state_store.get_state(session_id)
            if state is None:
                conversations.append(ConversationResults(session_id=session_id, conversation_completed=False,
                                                         conversation_conducted_at=None, experiences=[]))
                continue
            conversations.append(ConversationResults(
                session_id=session_id,
                conversation_completed=state.agent_director_state.current_phase == ConversationPhase.ENDED,
                conversation_conducted_at=state.agent_director_state.conversation_conducted_at,
                experiences=[ExperienceResponse.from_experience_entity(experience, DiveInPhase.PROCESSED)
                             for experience in state.explore_experiences_director_state.explored_experiences]))
        return ExternalUserResultsResponse(external_id=external_user.external_id, email=external_user.email,
                                           conversations=conversations)

    def _validate_webhook_url(self, url: str) -> None:
        if not self._webhooks_enabled:
            raise InvalidWebhookError("webhooks are not enabled on this instance.")
        try:
            validate_return_url(url, self._webhook_url_origins, field="webhook_url")
        except InvalidReturnUrlError as e:
            raise InvalidWebhookError(str(e)) from e

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
            await self._user_preferences_service.create_new_user_preferences(
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
