"""
Firebase Admin access for the integration API.

The users it creates are jobseekers, so they live in the default user pool of the frontend's Firebase project
(FIREBASE_PROJECT_ID), like the users who sign up in the browser. This is why app.admin.firebase.FirebaseService is not
reused: it works on the admin tenant of ADMIN_FIREBASE_PROJECT_ID, owns the default firebase_admin app and also opens a
Firestore client. This module uses its own named app instead, so both can run in the same process.
"""

import logging
import os
import secrets
from functools import cache
from typing import Optional

import firebase_admin
from firebase_admin import auth, credentials

_APP_NAME = "integration"

logger = logging.getLogger(__name__)


class IntegrationFirebase:
    """
    The Firebase Admin calls the integration API needs, on the default user pool of the frontend's Firebase project.
    """

    def __init__(self, project_id: str):
        try:
            self._app = firebase_admin.get_app(_APP_NAME)
        except ValueError:
            self._app = firebase_admin.initialize_app(credentials.ApplicationDefault(),
                                                      options={"projectId": project_id},
                                                      name=_APP_NAME)

    def get_user_by_email(self, email: str) -> Optional[auth.UserRecord]:
        try:
            return auth.get_user_by_email(email, app=self._app)
        except auth.UserNotFoundError:
            return None

    def get_user(self, user_id: str) -> Optional[auth.UserRecord]:
        try:
            return auth.get_user(user_id, app=self._app)
        except auth.UserNotFoundError:
            return None

    def create_user(self, email: str) -> auth.UserRecord:
        """
        Create a jobseeker account with a random password, as scripts/admin/onboard_pilot_users.py does. The calling
        platform vouches for the email on its own instance, so it is marked verified. The user enters through the
        hand-off link and can set a password later with "forgot password".
        """
        try:
            return auth.create_user(email=email,
                                    email_verified=True,
                                    password=secrets.token_urlsafe(32),
                                    disabled=False,
                                    app=self._app)
        except auth.EmailAlreadyExistsError:
            # a concurrent request created it first
            logger.info("Firebase user already exists, reusing it")
            return auth.get_user_by_email(email, app=self._app)

    def create_custom_token(self, user_id: str) -> str:
        """
        A custom token for signInWithCustomToken, without developer claims: the session gets only the claims that are
        already on the user record (see the eligibility guard).
        """
        return auth.create_custom_token(user_id, app=self._app).decode("utf-8")


@cache
def get_integration_firebase() -> IntegrationFirebase:
    return IntegrationFirebase(os.getenv("FIREBASE_PROJECT_ID"))
