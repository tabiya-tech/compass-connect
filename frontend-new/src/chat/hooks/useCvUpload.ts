import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSnackbar } from "src/theme/SnackbarProvider/SnackbarProvider";
import { nanoid } from "nanoid";
import type { IChatMessage } from "src/chat/Chat.types";
import type { UploadStatus } from "src/chat/Chat.types";
import { CANCELLABLE_CV_TYPING_CHAT_MESSAGE_TYPE, generateCancellableCVTypingMessage } from "src/chat/util";
import {
  getCvUploadDisplayMessage,
  getUploadErrorMessage,
  startUploadPolling,
  stopUploadPolling,
} from "src/chat/cvUploadPolling";
import { getCvUploadErrorMessageFromErrorCode } from "src/chat/CVUploadErrorHandling";
import { enqueueErrorSnackbarWithReference } from "src/theme/SnackbarProvider/enqueueErrorSnackbarWithReference";
import { ChatError } from "src/error/commonErrors";
import cvService from "src/CV/CVService/CVService";
import authenticationStateService from "src/auth/services/AuthenticationState.service";

export const MAX_UPLOAD_POLL_MS = 60 * 1000;

interface UseCvUploadOptions {
  addMessageToChat: (message: IChatMessage<any>) => void;
  removeMessageFromChat: (messageId: string) => void;
  setMessages: React.Dispatch<React.SetStateAction<IChatMessage<any>[]>>;
}

export interface UseCvUploadResult {
  isUploadingCv: boolean;
  cvUploadError: string | null;
  prefillMessage: string | null;
  activeUploadCount: number;
  handleUploadCv: (file: File) => Promise<string[]>;
  handleCancelUpload: (uploadId: string) => Promise<void>;
}

export const useCvUpload = ({
  addMessageToChat,
  removeMessageFromChat,
  setMessages,
}: UseCvUploadOptions): UseCvUploadResult => {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const [isUploadingCv, setIsUploadingCv] = useState(false);
  const [cvUploadError, setCvUploadError] = useState<string | null>(null);
  const [prefillMessage, setPrefillMessage] = useState<string | null>(null);
  const [activeUploads, setActiveUploads] = useState<
    Map<string, { messageId: string; intervalId: NodeJS.Timeout; timeoutId: NodeJS.Timeout }>
  >(new Map());

  // Tracks which message IDs have been disabled so isCancelled doesn't need to read messages state
  const disabledMessageIdsRef = useRef<Set<string>>(new Set());

  const stopPollingForUpload = useCallback(
    (uploadId: string, intervalId?: NodeJS.Timeout, timeoutId?: NodeJS.Timeout) => {
      stopUploadPolling(intervalId && timeoutId ? { intervalId, timeoutId } : undefined);
      setActiveUploads((prev) => {
        const next = new Map(prev);
        const existing = next.get(uploadId);
        if (existing) {
          stopUploadPolling({ intervalId: existing.intervalId, timeoutId: existing.timeoutId });
        }
        next.delete(uploadId);
        return next;
      });
    },
    []
  );

  const startPollingForUpload = useCallback(
    (uploadId: string, messageId: string) => {
      const existing = activeUploads.get(uploadId);
      if (existing) {
        stopPollingForUpload(uploadId, existing.intervalId, existing.timeoutId);
      }

      const handles = startUploadPolling({
        uploadId,
        pollIntervalMs: 2000,
        maxDurationMs: MAX_UPLOAD_POLL_MS,
        getStatus: async (id: string): Promise<UploadStatus> => {
          const userId = authenticationStateService.getInstance().getUser()?.id;
          if (!userId) throw new Error("User ID missing");
          const resp = await cvService.getInstance().getUploadStatus(userId, id);
          return {
            upload_process_state: resp.upload_process_state as UploadStatus["upload_process_state"],
            cancel_requested: resp.cancel_requested,
            filename: resp.filename,
            user_id: resp.user_id,
            upload_id: resp.upload_id,
            created_at: resp.created_at,
            last_activity_at: resp.last_activity_at,
            error_code: resp.error_code,
            error_detail: resp.error_detail,
            experience_bullets: resp.experience_bullets,
          } as UploadStatus;
        },
        onStatus: (status: UploadStatus | null) => {
          if (!status) return;
          const isDisabled =
            status.upload_process_state === "COMPLETED" ||
            status.upload_process_state === "CANCELLED" ||
            status.cancel_requested;
          if (isDisabled) {
            disabledMessageIdsRef.current.add(messageId);
          }
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.message_id === messageId && msg.type === CANCELLABLE_CV_TYPING_CHAT_MESSAGE_TYPE) {
                return {
                  ...msg,
                  payload: {
                    ...msg.payload,
                    message: getCvUploadDisplayMessage(status),
                    disabled: isDisabled,
                  },
                };
              }
              return msg;
            })
          );
        },
        onComplete: (status: UploadStatus) => {
          stopPollingForUpload(uploadId, handles.intervalId as any, handles.timeoutId as any);
          removeMessageFromChat(messageId);
          const items: string[] | undefined = status.experience_bullets ?? undefined;
          if (Array.isArray(items) && items.length > 0) {
            const intro = t("chat.util.messages.experiencesIntro");
            const bullets = items
              .map((s) => (s?.trim()?.length ? `• ${s.trim()}` : ""))
              .filter(Boolean)
              .join("\n");
            setPrefillMessage(bullets ? `${intro}\n${bullets}` : intro);
          }
          enqueueSnackbar(t("chat.cvUploadPolling.uploadedSuccessfully"), { variant: "success" });
        },
        onTerminal: (_status: UploadStatus) => {
          stopPollingForUpload(uploadId, handles.intervalId as any, handles.timeoutId as any);
          setTimeout(() => removeMessageFromChat(messageId), 3000);
          setPrefillMessage(null);
          setCvUploadError(getCvUploadErrorMessageFromErrorCode(_status));
        },
        onError: (error: unknown) => {
          stopPollingForUpload(uploadId, handles.intervalId as any, handles.timeoutId as any);
          setPrefillMessage(null);
          const err = error as {
            status?: number;
            response?: { status?: number; data?: { detail?: string } };
            message?: string;
          };
          const statusCode = err?.status || err?.response?.status;
          const detail = err?.response?.data?.detail || err?.message;
          if (statusCode === 404 || err?.message === "timeout") {
            removeMessageFromChat(messageId);
            enqueueSnackbar(getUploadErrorMessage(404, detail), { variant: "warning" });
            return;
          }
          if (statusCode === 409) {
            removeMessageFromChat(messageId);
            enqueueSnackbar(getUploadErrorMessage(409, detail), { variant: "warning" });
            return;
          }
          if (statusCode === 429) {
            enqueueSnackbar(getUploadErrorMessage(429, detail), { variant: "warning" });
          } else if (statusCode) {
            enqueueErrorSnackbarWithReference(getUploadErrorMessage(statusCode, detail), {
              where: "CV upload (polling)",
              error,
            });
          } else {
            enqueueErrorSnackbarWithReference(t("chat.cvUploadPolling.networkErrorStatus"), {
              where: "CV upload (polling)",
              error,
            });
          }
          console.error("Error polling upload status:", error);
        },
        isCancelled: () => disabledMessageIdsRef.current.has(messageId),
      });

      setActiveUploads((prev) =>
        new Map(prev).set(uploadId, {
          messageId,
          intervalId: handles.intervalId as any,
          timeoutId: handles.timeoutId as any,
        })
      );
    },
    [activeUploads, enqueueSnackbar, removeMessageFromChat, setMessages, stopPollingForUpload, t]
  );

  const handleCancelUpload = useCallback(
    async (uploadId: string) => {
      try {
        // Temporary ID used before the real uploadId is returned from the backend
        if (uploadId === "chat.chatMessageField.placeholders.uploading") {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.type === CANCELLABLE_CV_TYPING_CHAT_MESSAGE_TYPE && !msg.payload.disabled) {
                return {
                  ...msg,
                  payload: { ...msg.payload, message: t("chat.cvUploadPolling.cancelled"), disabled: true },
                };
              }
              return msg;
            })
          );
          enqueueSnackbar(t("chat.cvUploadPolling.cancelled"), { variant: "info" });
          return;
        }

        const userId = authenticationStateService.getInstance().getUser()?.id;
        if (!userId) return;

        await cvService.getInstance().cancelUpload(userId, uploadId);

        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.message_id === activeUploads.get(uploadId)?.messageId) {
              return {
                ...msg,
                payload: { ...msg.payload, message: t("chat.cvUploadPolling.cancelled"), disabled: true },
              };
            }
            return msg;
          })
        );

        const uploadInfo = activeUploads.get(uploadId);
        if (uploadInfo) {
          stopPollingForUpload(uploadId, uploadInfo.intervalId, uploadInfo.timeoutId);
        }

        enqueueSnackbar(t("chat.cvUploadPolling.cancelled"), { variant: "info" });
      } catch (error) {
        console.error("Error cancelling upload:", error);
        enqueueErrorSnackbarWithReference(t("chat.cvUploadPolling.failedToCancel"), {
          where: "CV upload (cancel)",
          error,
        });
      }
    },
    [activeUploads, enqueueSnackbar, setMessages, stopPollingForUpload, t]
  );

  const handleUploadCv = useCallback(
    async (file: File): Promise<string[]> => {
      if (isUploadingCv) return [];

      setIsUploadingCv(true);
      const uploadingMessageId = nanoid();

      try {
        setPrefillMessage(null);
        setCvUploadError(null);
        enqueueSnackbar(t("chat.cvUploadPolling.uploadingFileNamed", { filename: file.name }), { variant: "info" });

        const userId = authenticationStateService.getInstance().getUser()?.id;
        if (!userId) throw new ChatError("User ID is not available");

        addMessageToChat({
          ...generateCancellableCVTypingMessage(
            "chat.chatMessageField.placeholders.uploading",
            handleCancelUpload,
            false,
            false,
            "UPLOADING"
          ),
          message_id: uploadingMessageId,
        });

        const response = await cvService.getInstance().uploadCV(userId, file);

        if (response.uploadId) {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.message_id === uploadingMessageId && msg.type === CANCELLABLE_CV_TYPING_CHAT_MESSAGE_TYPE) {
                return {
                  ...msg,
                  payload: { ...msg.payload, onCancel: async () => handleCancelUpload(response.uploadId!) },
                };
              }
              return msg;
            })
          );
          try {
            const userIdVerify = authenticationStateService.getInstance().getUser()?.id;
            if (!userIdVerify) throw new Error("User ID missing");
            await cvService.getInstance().getUploadStatus(userIdVerify, response.uploadId);
            startPollingForUpload(response.uploadId, uploadingMessageId);
          } catch (err: any) {
            console.error("Failed to verify upload status", err);
            const statusCode = err?.status || err?.response?.status;
            const detail = err?.response?.data?.detail || err?.message;
            removeMessageFromChat(uploadingMessageId);
            enqueueSnackbar(getUploadErrorMessage(statusCode, detail), {
              variant: statusCode && statusCode < 500 ? "warning" : "error",
            });
            return [];
          }
        } else {
          removeMessageFromChat(uploadingMessageId);
          console.log("Failed to start upload. Backend did not return uploadId ", response);
          enqueueErrorSnackbarWithReference(t("chat.cvUploadPolling.failedToStart"), {
            where: "CV upload (start)",
            error: new Error("Backend did not return an uploadId"),
          });
          return [];
        }

        return [];
      } catch (e: any) {
        console.error(new ChatError("CV upload failed", e));
        removeMessageFromChat(uploadingMessageId);
        setPrefillMessage(null);
        throw e;
      } finally {
        setIsUploadingCv(false);
      }
    },
    [
      addMessageToChat,
      enqueueSnackbar,
      handleCancelUpload,
      isUploadingCv,
      removeMessageFromChat,
      setMessages,
      startPollingForUpload,
      t,
    ]
  );

  // Cleanup all polling intervals when the component using this hook unmounts
  useEffect(() => {
    return () => {
      activeUploads.forEach(({ intervalId }) => clearInterval(intervalId));
    };
  }, [activeUploads]);

  return {
    isUploadingCv,
    cvUploadError,
    prefillMessage,
    activeUploadCount: activeUploads.size,
    handleUploadCv,
    handleCancelUpload,
  };
};
