import React, { startTransition, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Box, CircularProgress, Typography } from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";
import { routerPaths } from "src/app/routerPaths";
import { isAcceptedTCValid } from "src/app/ProtectedRoute/util";
import AuthenticationServiceFactory from "src/auth/services/Authentication.service.factory";
import AuthenticationStateService from "src/auth/services/AuthenticationState.service";
import FirebaseCustomTokenAuthenticationService from "src/auth/services/FirebaseAuthenticationService/customTokenAuth/FirebaseCustomTokenAuthenticationService";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import HandoffService from "src/handoff/handoff.service";
import { HandoffAction } from "src/handoff/handoff.types";
import PrimaryButton from "src/theme/PrimaryButton/PrimaryButton";
import { AuthenticationError } from "src/error/commonErrors";
import { ConsentPageState } from "src/consent/components/consentPage/Consent";

const uniqueId = "7c1e5a9b-3d42-4f8e-9a61-2b0d4e8f6c13";

export const DATA_TEST_ID = {
  HANDOFF_CONTAINER: `handoff-container-${uniqueId}`,
  LOADING_SPINNER: `handoff-loading-${uniqueId}`,
  ERROR_TITLE: `handoff-error-title-${uniqueId}`,
  ERROR_MESSAGE: `handoff-error-message-${uniqueId}`,
  BACK_TO_LOGIN_BUTTON: `handoff-back-to-login-${uniqueId}`,
};

export const HANDOFF_TOKEN_PARAM_NAME = "token";

/**
 * Logs the user in with the hand-off link token. Whoever is logged in on this device (e.g. a shared phone, or the same
 * user sent through the same button again) is logged out first.
 * @returns where the user lands
 */
export async function logInWithHandoffLink(token: string): Promise<HandoffAction> {
  const { custom_token, action } = await HandoffService.getInstance().exchange(token);

  if (AuthenticationStateService.getInstance().getUser()) {
    await AuthenticationServiceFactory.getCurrentAuthenticationService()?.logout();
  }
  await FirebaseCustomTokenAuthenticationService.getInstance().login(custom_token);
  return action;
}

/**
 * Landing page of the hand-off link (/#/handoff?token=...): another platform sends a user here to log them in and take
 * them to the home page or the conversation.
 */
const Handoff: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const token = new URLSearchParams(location.search).get(HANDOFF_TOKEN_PARAM_NAME);
    // remove the token from the URL (and the history) right away
    navigate({ pathname: location.pathname, search: "" }, { replace: true });
    if (!token) {
      setFailed(true);
      return;
    }

    logInWithHandoffLink(token)
      .then((action) => {
        const landingPath = action === HandoffAction.BUILD_PROFILE ? routerPaths.SKILLS_INTERESTS : routerPaths.ROOT;
        const prefs = UserPreferencesStateService.getInstance().getUserPreferences();
        if (!prefs || !isAcceptedTCValid(prefs)) {
          // first visit: the consent page comes first, then the landing page
          const state: ConsentPageState = { afterConsent: landingPath };
          navigate(routerPaths.CONSENT, { replace: true, state });
          return;
        }
        // the chat is lazy loaded: navigate in a transition, or React fails while it loads
        startTransition(() => {
          navigate(landingPath, { replace: true });
        });
      })
      .catch((e) => {
        console.error(new AuthenticationError("Hand-off login failed", e));
        setFailed(true);
      });
  }, [location, navigate]);

  return (
    <Box
      data-testid={DATA_TEST_ID.HANDOFF_CONTAINER}
      display="flex"
      flexDirection="column"
      justifyContent="center"
      alignItems="center"
      gap={2}
      minHeight="50vh"
      padding={2}
      textAlign="center"
    >
      {failed ? (
        <>
          <Typography variant="h5" data-testid={DATA_TEST_ID.ERROR_TITLE}>
            {t("auth.pages.handoff.invalidLinkTitle")}
          </Typography>
          <Typography data-testid={DATA_TEST_ID.ERROR_MESSAGE}>{t("auth.pages.handoff.invalidLinkMessage")}</Typography>
          <PrimaryButton
            data-testid={DATA_TEST_ID.BACK_TO_LOGIN_BUTTON}
            onClick={() => navigate(routerPaths.LOGIN, { replace: true })}
          >
            {t("common.buttons.backToLogin")}
          </PrimaryButton>
        </>
      ) : (
        <>
          <CircularProgress data-testid={DATA_TEST_ID.LOADING_SPINNER} />
          <Typography>{t("auth.pages.handoff.signingIn")}</Typography>
        </>
      )}
    </Box>
  );
};

export default Handoff;
