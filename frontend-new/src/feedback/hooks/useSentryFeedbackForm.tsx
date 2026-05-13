import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import * as Sentry from "@sentry/react";
import authenticationStateService from "src/auth/services/AuthenticationState.service";
import { PersistentStorageService } from "src/app/PersistentStorageService/PersistentStorageService";
import { useSnackbar } from "src/theme/SnackbarProvider/SnackbarProvider";
import FeedbackModal, { FeedbackModalSubmitPayload } from "src/feedback/feedbackModal/FeedbackModal";

interface OpenFeedbackFormOptions {
  markNotificationSeen?: boolean;
}

interface UseSentryFeedbackFormOptions {
  markNotificationSeenOnOpen?: boolean;
}

// Capture a PNG screenshot of the document body.
// Excludes any node inside a MUI modal (".MuiModal-root") so the feedback
// dialog itself is not in the screenshot when capturing happens after it opens.
const captureScreenshot = async (): Promise<{ bytes: Uint8Array; dataUrl: string } | null> => {
  try {
    const { toPng } = await import("html-to-image");
    const dataUrl = await toPng(document.body, {
      cacheBust: true,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
      filter: (node) => {
        const el = node as HTMLElement;
        if (!el.classList) return true;
        return !el.classList.contains("MuiModal-root");
      },
    });
    const base64 = dataUrl.split(",", 2)[1] ?? "";
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return { bytes, dataUrl };
  } catch (error) {
    console.warn("Failed to capture feedback screenshot:", error);
    return null;
  }
};

export const useSentryFeedbackForm = (options: UseSentryFeedbackFormOptions = {}) => {
  const { markNotificationSeenOnOpen = false } = options;
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const [sentryEnabled, setSentryEnabled] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [screenshot, setScreenshot] = useState<{ bytes: Uint8Array; dataUrl: string } | null>(null);

  useEffect(() => {
    setSentryEnabled(Sentry.isInitialized());
  }, []);

  // Trigger capture once the modal is open. Running after commit ensures the
  // Dialog is mounted, so the .MuiModal-root filter excludes it from the snapshot.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setIsCapturing(true);
    captureScreenshot().then((result) => {
      if (cancelled) return;
      setScreenshot(result);
      setIsCapturing(false);
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const openFeedbackForm = useCallback(
    async (openOptions: OpenFeedbackFormOptions = {}): Promise<boolean> => {
      if (!sentryEnabled) {
        console.debug("Sentry is not initialized, feedback form cannot be created.");
        return false;
      }

      const shouldMarkAsSeen = openOptions.markNotificationSeen ?? markNotificationSeenOnOpen;
      if (shouldMarkAsSeen) {
        const user = authenticationStateService.getInstance().getUser();
        if (user) {
          PersistentStorageService.setSeenFeedbackNotification(user.id);
        }
      }

      setIsOpen(true);
      return true;
    },
    [markNotificationSeenOnOpen, sentryEnabled]
  );

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setScreenshot(null);
    setIsCapturing(false);
  }, []);

  const handleRemoveScreenshot = useCallback(() => {
    setScreenshot(null);
  }, []);

  const handleSubmit = useCallback(
    (payload: FeedbackModalSubmitPayload) => {
      try {
        const user = authenticationStateService.getInstance().getUser();
        const attachments = payload.screenshot
          ? [
              {
                filename: "screenshot.png",
                data: payload.screenshot,
                contentType: "image/png",
              },
            ]
          : undefined;
        Sentry.captureFeedback(
          {
            name: user?.name,
            email: user?.email,
            message: payload.message,
            tags: {
              "feedback.type": payload.type,
              "feedback.priority": payload.priority,
            },
          },
          { includeReplay: true, attachments }
        );
        enqueueSnackbar(t("feedback.feedbackModal.successMessage"), { variant: "success" });
      } catch (error) {
        console.error("Error sending feedback to Sentry:", error);
        enqueueSnackbar(t("feedback.feedbackModal.errorMessage"), { variant: "error" });
      }
    },
    [enqueueSnackbar, t]
  );

  const feedbackModalElement = useMemo(
    () => (
      <FeedbackModal
        isOpen={isOpen}
        onClose={handleClose}
        onSubmit={handleSubmit}
        screenshotDataUrl={screenshot?.dataUrl ?? null}
        screenshotBytes={screenshot?.bytes ?? null}
        isCapturingScreenshot={isCapturing}
        onRemoveScreenshot={handleRemoveScreenshot}
      />
    ),
    [isOpen, handleClose, handleSubmit, screenshot, isCapturing, handleRemoveScreenshot]
  );

  return {
    sentryEnabled,
    openFeedbackForm,
    feedbackModalElement,
  };
};
