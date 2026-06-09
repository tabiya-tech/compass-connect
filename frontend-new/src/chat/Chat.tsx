import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ChatService from "src/chat/ChatService/ChatService";
import { IChatMessage } from "src/chat/Chat.types";
import { BWS_TASK_MESSAGE_TYPE } from "src/chat/chatMessage/bwsTaskMessage/BWSTaskMessage";
import {
  generateConversationConclusionMessage,
  generateSomethingWentWrongMessage,
  generateTypingMessage,
  generateUserMessage,
  mapConversationMessagesToChatMessages,
  parseConversationPhase,
} from "./util";
import { useSnackbar } from "src/theme/SnackbarProvider/SnackbarProvider";
import { Box, useTheme } from "@mui/material";
import ChatHeader from "src/chat/ChatHeader/ChatHeader";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import { ConversationMessage, ConversationResponse } from "./ChatService/ChatService.types";
import { Backdrop } from "src/theme/Backdrop/Backdrop";
import { DiveInPhase } from "src/experiences/experienceService/experiences.types";
import InactiveBackdrop from "src/theme/Backdrop/InactiveBackdrop";
import ConfirmModalDialog from "src/theme/confirmModalDialog/ConfirmModalDialog";
import { ChatError, MetricsError } from "src/error/commonErrors";
import authenticationStateService from "src/auth/services/AuthenticationState.service";
import { ensureSessionForUser } from "./ensureSession";
import { issueNewSession } from "./issueNewSession";
import { getNewSessionEnabled, getProductName } from "src/envService";
import { useRebuildProfile } from "./RebuildProfileContext";
import { ChatProvider } from "src/chat/ChatContext";
import { lazyWithPreload } from "src/utils/preloadableComponent/PreloadableComponent";
import { ConversationPhase, CurrentPhase, defaultCurrentPhase } from "./chatProgressbar/types";
import { AgentChatMessageProps } from "./chatMessage/agentChatMessage/AgentChatMessage";
import { SkillsRankingService } from "src/features/skillsRanking/skillsRankingService/skillsRankingService";
import { useSkillsRanking } from "src/features/skillsRanking/hooks/useSkillsRanking";
import MetricsService from "src/metrics/metricsService";
import { EventType } from "src/metrics/types";
import { getNetworkInformation } from "src/metrics/utils/getNetworkInformation";
import { enqueueErrorSnackbarWithReference } from "src/theme/SnackbarProvider/enqueueErrorSnackbarWithReference";
import { nanoid } from "nanoid";
import { useExperiencesDrawer } from "src/experiences/ExperiencesDrawerProvider";
import ModuleHandoffBanner from "src/home/components/ModuleHandoffBanner/ModuleHandoffBanner";
import { useNextModule } from "src/home/useNextModule";
import ChatPage from "src/chat/ChatPage/ChatPage";
import SkillsDiscoverySidebar from "src/home/components/Sidebar/SkillsDiscoverySidebar";
import { useCvUpload } from "src/chat/hooks/useCvUpload";
import { useInactivityBackdrop } from "src/chat/hooks/useInactivityBackdrop";
import { useRefreshGuard } from "src/chat/hooks/useRefreshGuard";

export { INACTIVITY_TIMEOUT, CHECK_INACTIVITY_INTERVAL } from "src/chat/hooks/useInactivityBackdrop";
export { MAX_UPLOAD_POLL_MS } from "src/chat/hooks/useCvUpload";

export const FEEDBACK_NOTIFICATION_DELAY = 30 * 60 * 1000; // In milliseconds
// Always add an artificial typing message for the conclusion message
export const TYPING_BEFORE_CONCLUSION_MESSAGE_TIMEOUT = 3000; // In milliseconds

const uniqueId = "b7ea1e82-0002-432d-a768-11bdcd186e1d";
export const DATA_TEST_ID = {
  CONTAINER: `container-${uniqueId}`,
  CHAT_CONTAINER: `chat-container-${uniqueId}`,
};

// i18n notification message keys (tests/components should resolve via t(<key>))
export const NOTIFICATION_MESSAGES_TEXT = {
  NEW_CONVERSATION_STARTED: "chat.chat.notifications.startConversationSuccess",
  SUCCESSFULLY_LOGGED_OUT: "chat.chat.notifications.logoutSuccess",
  FAILED_TO_START_CONVERSATION: "chat.chat.notifications.startConversationFailed",
} as const;

interface ChatProps {
  showInactiveSessionAlert?: boolean;
  disableInactivityCheck?: boolean;
}

const createShowConclusionMessage = (
  lastMessage: ConversationMessage,
  addMessageToChat: (message: IChatMessage<any>) => void,
  setAiIsTyping: (isTyping: boolean) => void,
  skipTyping: boolean = false
) => {
  return () => {
    const conclusionMessage = generateConversationConclusionMessage(lastMessage.message_id, lastMessage.message);

    // Skip typing message when skills ranking is already completed
    if (skipTyping) {
      addMessageToChat(conclusionMessage);
    } else {
      setAiIsTyping(true);
      setTimeout(() => {
        setAiIsTyping(false);
        addMessageToChat(conclusionMessage);
      }, TYPING_BEFORE_CONCLUSION_MESSAGE_TIMEOUT);
    }
  };
};

const handleConclusionFlow = async (
  sessionId: number,
  lastMessage: ConversationMessage,
  addMessageToChat: (message: IChatMessage<any>) => void,
  setAiIsTyping: (typing: boolean) => void,
  showSkillsRanking: (showConclusion: () => void) => Promise<void>
): Promise<void> => {
  if (SkillsRankingService.getInstance().isSkillsRankingFeatureEnabled()) {
    const skillsRankingState = await SkillsRankingService.getInstance().getSkillsRankingState(sessionId);
    const isAlreadyCompleted = skillsRankingState?.completed_at !== undefined;
    await showSkillsRanking(
      createShowConclusionMessage(lastMessage, addMessageToChat, setAiIsTyping, isAlreadyCompleted)
    );
  } else {
    addMessageToChat(generateConversationConclusionMessage(lastMessage.message_id, lastMessage.message));
  }
};

export const Chat: React.FC<Readonly<ChatProps>> = ({
  showInactiveSessionAlert = false,
  disableInactivityCheck = false,
}) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const [messages, setMessages] = useState<IChatMessage<any>[]>([]);
  const [conversationCompleted, setConversationCompleted] = useState<boolean>(false);
  const nextModule = useNextModule("skills_discovery");
  const [exploredExperiences, setExploredExperiences] = useState<number>(0);
  const [aiIsTyping, setAiIsTyping] = useState<boolean>(false);
  const [failedSendDraft, setFailedSendDraft] = useState<string | null>(null);
  const [newConversationDialog, setNewConversationDialog] = React.useState<boolean>(false);
  const [exploredExperiencesNotification, setExploredExperiencesNotification] = useState<boolean>(false);
  const newSessionEnabled = getNewSessionEnabled();
  const appName = getProductName();
  const networkInfoSentRef = useRef<boolean>(false);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(
    UserPreferencesStateService.getInstance().getActiveSessionId()
  );
  const [currentUserId] = useState<string | null>(authenticationStateService.getInstance().getUser()?.id ?? null);
  const [currentPhase, setCurrentPhase] = useState<CurrentPhase>(defaultCurrentPhase);
  const [sidebarRefreshToken, setSidebarRefreshToken] = useState(0);

  const initializingRef = useRef(false);
  const handleQuickReplyRef = useRef<(label: string) => void>(() => {});
  const [initialized, setInitialized] = useState<boolean>(false);
  // Stable ref for handleBWSSubmit — avoids a circular dep between sendMessage and handleBWSSubmit
  const handleBWSSubmitRef = useRef<((taskId: string, bestWaId: string, worstWaId: string) => Promise<void>) | null>(
    null
  );

  const { experiences, fetchExperiences, openExperiencesDrawer, setConversationConductedAt } = useExperiencesDrawer();
  const { registerRebuildProfile } = useRebuildProfile();

  // Experiences that have been processed
  const exploredExperiencesCount = useMemo(
    () => (experiences ?? []).filter((experience) => experience.exploration_phase === DiveInPhase.PROCESSED),
    [experiences]
  );

  /**
   * --- Utility functions ---
   */

  const addMessageToChat = useCallback((message: IChatMessage<any>) => {
    setMessages((prevMessages) => [...prevMessages, message]);
  }, []);

  const removeMessageFromChat = useCallback((messageId: string) => {
    setMessages((prevMessages) => prevMessages.filter((msg) => msg.message_id !== messageId));
  }, []);

  const { showSkillsRanking } = useSkillsRanking(addMessageToChat, removeMessageFromChat);

  // --- Hooks extracted from this component ---

  const { isUploadingCv, cvUploadError, prefillMessage, activeUploadCount, handleUploadCv } = useCvUpload({
    addMessageToChat,
    removeMessageFromChat,
    setMessages,
  });

  const showBackdrop = useInactivityBackdrop({
    initiallyShown: showInactiveSessionAlert,
    disabled: disableInactivityCheck,
    conversationCompleted,
  });

  const { showConfirmDialog: showRefreshDialog, confirmRefresh, cancelRefresh } = useRefreshGuard(aiIsTyping);

  // --- Metrics ---

  useEffect(() => {
    if (!currentUserId || networkInfoSentRef.current) return;
    try {
      const networkInfo = getNetworkInformation();
      MetricsService.getInstance().sendMetricsEvent({
        event_type: EventType.NETWORK_INFORMATION,
        user_id: currentUserId,
        effective_connection_type: networkInfo.effectiveConnectionType,
        connection_type: networkInfo.connectionType,
      });
      networkInfoSentRef.current = true;
    } catch (error) {
      console.error(new MetricsError("Failed to send network information metrics", error));
    }
  }, [currentUserId]);

  const recordChatResponseMetrics = useCallback(
    ({
      sessionId,
      userMessage,
      response,
      durationMs,
      previousExploredExperiences,
    }: {
      sessionId: number;
      userMessage: string;
      response: ConversationResponse;
      durationMs: number;
      previousExploredExperiences: number;
    }) => {
      if (!currentUserId) {
        console.error(new MetricsError("Unable to send chat timing metrics: user id is missing"));
        return;
      }

      try {
        const networkInfo = getNetworkInformation();
        MetricsService.getInstance().sendMetricsEvent({
          event_type: EventType.UI_INTERACTION,
          user_id: currentUserId,
          actions: ["chat_response_time"],
          element_id: "chat-send-message",
          timestamp: new Date().toISOString(),
          relevant_experiments: {},
          details: {
            duration_ms: durationMs,
            session_id: sessionId,
            message_length: userMessage.length,
            response_messages: response.messages.length,
            conversation_completed: response.conversation_completed,
            conversation_phase: response.current_phase?.phase,
            conversation_phase_percent: response.current_phase?.percentage,
            experiences_explored: response.experiences_explored,
            experiences_explored_delta: response.experiences_explored - previousExploredExperiences,
            network_effective_type: networkInfo.effectiveConnectionType,
            network_connection_type: networkInfo.connectionType,
            network_rtt_ms: networkInfo.rtt,
            network_downlink_mbps: networkInfo.downlink,
            network_save_data: networkInfo.saveData,
          },
        });
      } catch (error) {
        console.error(new MetricsError("Unable to send chat timing metrics", error));
      }
    },
    [currentUserId]
  );

  // --- Typing indicator ---

  const addOrRemoveTypingMessage = useCallback(
    (isTyping: boolean) => {
      if (isTyping) {
        const thinkingMessage =
          currentPhase.phase === ConversationPhase.PREFERENCE_ELICITATION
            ? t("chat.chatMessage.typingChatMessage.thinkingPreferenceElicitation")
            : undefined;
        setMessages((prev) => {
          const hasTypingMessage = prev[prev.length - 1]?.type?.startsWith("typing-message-") ?? false;
          return hasTypingMessage ? prev : [...prev, generateTypingMessage(undefined, thinkingMessage)];
        });
      } else {
        setMessages((prev) => prev.filter((msg) => !msg.type.startsWith("typing-message-")));
      }
    },
    [currentPhase.phase, t]
  );

  useEffect(() => {
    addOrRemoveTypingMessage(aiIsTyping);
  }, [aiIsTyping, addOrRemoveTypingMessage]);

  // --- Derived state ---

  const isAwaitingBWSResponse = useMemo(
    () => messages.length > 0 && messages[messages.length - 1].type === BWS_TASK_MESSAGE_TYPE,
    [messages]
  );

  const timeUntilFeedbackNotification: number | null = useMemo(() => {
    // If there are no messages, we can't calculate the time
    if (messages.length === 0) return null;
    const firstAgentMessage = messages.find((m) => m.type.startsWith("agent-message-")) as
      | IChatMessage<AgentChatMessageProps>
      | undefined;
    if (!firstAgentMessage?.payload.sent_at) return null;
    const targetTime = new Date(firstAgentMessage.payload.sent_at).getTime() + FEEDBACK_NOTIFICATION_DELAY;
    return Math.max(0, targetTime - Date.now());
  }, [messages]);

  const quickReplyOptions = useMemo(() => {
    const lastMessage = messages[messages.length - 1];
    return lastMessage?.payload?.quick_reply_options || null;
  }, [messages]);

  // --- Quick reply + BWS ---

  const handleQuickReply = useCallback((label: string) => {
    handleQuickReplyRef.current(label);
  }, []);

  // --- Message sending ---

  const bwsSubmitHandler = useCallback(
    (taskId: string, bestWaId: string, worstWaId: string) =>
      handleBWSSubmitRef.current?.(taskId, bestWaId, worstWaId) ?? Promise.resolve(),
    []
  );

  const sendMessage = useCallback(
    async (userMessage: string, sessionId: number, displayMessage?: string) => {
      setAiIsTyping(true);
      // Clear quick-reply buttons from all messages when user sends a new message
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.payload?.quick_reply_options) {
            return { ...msg, payload: { ...msg.payload, quick_reply_options: null } };
          }
          return msg;
        })
      );
      // displayMessage="" suppresses the bubble; undefined = use userMessage as display
      const chatText = displayMessage !== undefined ? displayMessage : userMessage;
      let optimisticMessageId: string | undefined;
      if (chatText) {
        optimisticMessageId = nanoid();
        const message = generateUserMessage(
          chatText,
          new Date().toISOString(),
          theme.palette.secondary.main,
          theme.palette.secondary.contrastText,
          optimisticMessageId
        );
        addMessageToChat(message);
      }

      const startTimeMs = typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
      const previousExploredExperiences = exploredExperiences;

      try {
        setFailedSendDraft(null);
        const response = await ChatService.getInstance().sendMessage(sessionId, userMessage);
        const durationMs = Math.round(
          (typeof performance !== "undefined" && performance.now ? performance.now() : Date.now()) - startTimeMs
        );
        recordChatResponseMetrics({ sessionId, userMessage, response, durationMs, previousExploredExperiences });

        setExploredExperiences(response.experiences_explored);
        if (response.experiences_explored > exploredExperiences) {
          setExploredExperiencesNotification(true);
          await fetchExperiences();
        }

        // Filter out the conclusion message before mapping — it's handled separately
        const nonConclusionMessages = response.messages.filter(
          (_, idx) => !(response.conversation_completed && idx === response.messages.length - 1)
        );
        const mapped = mapConversationMessagesToChatMessages(nonConclusionMessages, {
          userFillColor: theme.palette.secondary.main,
          userTextColor: theme.palette.secondary.contrastText,
          onBWSSubmit: bwsSubmitHandler,
          onQuickReply: handleQuickReply,
          bwsTransitionMessage: t("chat.chat.bwsTransitionMessage"),
        });
        mapped.forEach(addMessageToChat);

        if (response.conversation_completed && response.messages.length) {
          await handleConclusionFlow(
            sessionId,
            response.messages[response.messages.length - 1],
            addMessageToChat,
            setAiIsTyping,
            showSkillsRanking
          );
        }

        setConversationCompleted(response.conversation_completed);
        setConversationConductedAt(response.conversation_conducted_at);
        setSidebarRefreshToken((prev) => prev + 1);
        setCurrentPhase((prev) => parseConversationPhase(response.current_phase, prev));
      } catch (error) {
        console.error(new ChatError("Failed to send message:", error));
        if (optimisticMessageId) removeMessageFromChat(optimisticMessageId);
        if (chatText) setFailedSendDraft(chatText);
        enqueueErrorSnackbarWithReference(t("common.errors.api.unexpectedError"), {
          where: "Chat conversation (send)",
          error: error as Error,
        });
      } finally {
        setAiIsTyping(false);
      }
    },
    [
      t,
      theme,
      addMessageToChat,
      removeMessageFromChat,
      exploredExperiences,
      fetchExperiences,
      showSkillsRanking,
      recordChatResponseMetrics,
      handleQuickReply,
      setConversationConductedAt,
      bwsSubmitHandler,
    ]
  );

  const initializeChat = useCallback(
    async (userId: string | null, currentSessionId: number | null) => {
      if (!userId) {
        console.error(new ChatError("Chat cannot be initialized, there is not User id  not available"));
        return false;
      }

      setAiIsTyping(true);
      let sessionId: number | null = currentSessionId;

      try {
        if (!sessionId) {
          sessionId = newSessionEnabled ? await issueNewSession(userId) : await ensureSessionForUser(userId);
          if (sessionId) {
            // Clear the messages if a new session is issued
            //  and add a typing message as the previous one will be removed
            setMessages([generateTypingMessage()]);
            // AND clear the current phase
            setCurrentPhase(defaultCurrentPhase);
          } else {
            return false;
          }
        }

        // Get the chat history
        const history = await ChatService.getInstance().getChatHistory(sessionId);

        // Set the messages from the chat history
        if (history.messages.length) {
          // Separate the last message if it's a conclusion
          const isConclusionMessage = history.conversation_completed;
          const filteredMessages = history.messages.filter(
            (_, idx) => !(isConclusionMessage && idx === history.messages.length - 1)
          );
          const mappedMessages = mapConversationMessagesToChatMessages(filteredMessages, {
            userFillColor: theme.palette.secondary.main,
            userTextColor: theme.palette.secondary.contrastText,
            onBWSSubmit: bwsSubmitHandler,
            onQuickReply: handleQuickReply,
            bwsTransitionMessage: t("chat.chat.bwsTransitionMessage"),
          });
          setMessages(mappedMessages);

          if (isConclusionMessage) {
            await handleConclusionFlow(
              sessionId,
              history.messages[history.messages.length - 1],
              addMessageToChat,
              setAiIsTyping,
              showSkillsRanking
            );
          }

          setConversationCompleted(history.conversation_completed);
          setConversationConductedAt(history.conversation_conducted_at);
        } else {
          // if this is the last promise to resolve, we should not set any state before it is resolved
          // This is the first message to kick off the conversation
          await sendMessage("", sessionId);
        }

        // IMPORTANT: set state only after all promises are resolved

        // Set the explored experiences state
        setExploredExperiences(history.experiences_explored);
        setExploredExperiencesNotification(history.experiences_explored > 0);

        // Set the active session id state
        setActiveSessionId(sessionId);

        // Set the current conversation phase
        setCurrentPhase((_previousCurrentPhase) => {
          return parseConversationPhase(history.current_phase, _previousCurrentPhase);
        });
        return true;
      } catch (e) {
        console.error(new ChatError("Failed to initialize chat", e));
        return false;
      } finally {
        setAiIsTyping(false);
      }
    },
    [
      addMessageToChat,
      showSkillsRanking,
      sendMessage,
      handleQuickReply,
      setConversationConductedAt,
      theme,
      newSessionEnabled,
      t,
      bwsSubmitHandler,
    ]
  );

  const handleConfirmNewConversation = useCallback(async () => {
    setNewConversationDialog(false);
    setExploredExperiencesNotification(false);
    if (await initializeChat(currentUserId, null)) {
      enqueueSnackbar(t("chat.chat.notifications.startConversationSuccess"), { variant: "success" });
    } else {
      // Add a message to the chat saying that something went wrong
      setMessages([generateSomethingWentWrongMessage()]);
      // Set the conversation as completed to prevent the user from sending any messages
      setConversationCompleted(true);
      // Notify the user that the chat failed to start
      enqueueSnackbar(t("chat.chat.notifications.startConversationFailed"), { variant: "error" });
    }
  }, [enqueueSnackbar, initializeChat, currentUserId, t]);

  const handleSend = useCallback(
    async (userMessage: string) => {
      await sendMessage(userMessage, activeSessionId!);
    },
    [sendMessage, activeSessionId]
  );

  // Handles BWS task card submission — encodes the selection as JSON and sends via the normal message path
  const handleBWSSubmit = useCallback(
    async (taskId: string, bestWaId: string, worstWaId: string) => {
      const payload = JSON.stringify({ type: "bws_response", task_id: taskId, best: bestWaId, worst: worstWaId });
      // Pass "" as displayMessage to suppress the raw JSON from appearing in the chat
      await sendMessage(payload, activeSessionId!, "");
    },
    [sendMessage, activeSessionId]
  );
  handleBWSSubmitRef.current = handleBWSSubmit;

  // Keep the quick-reply ref pointing at the latest handleSend
  useEffect(() => {
    handleQuickReplyRef.current = handleSend;
  }, [handleSend]);

  // --- Effects ---

  useEffect(() => {
    if (newSessionEnabled) {
      registerRebuildProfile(() => setNewConversationDialog(true));
      return () => registerRebuildProfile(null);
    }
  }, [newSessionEnabled, registerRebuildProfile]);

  useEffect(() => {
    if (initializingRef.current) return;
    initializingRef.current = true;
    initializeChat(currentUserId, activeSessionId).then((successful) => {
      if (!successful) {
        setMessages([generateSomethingWentWrongMessage()]);
        setConversationCompleted(true);
        enqueueErrorSnackbarWithReference(t("chat.chat.notifications.startConversationFailed"), {
          where: "Chat conversation (start)",
          error: new Error("initializeChat returned false"),
        });
      }
      setInitialized(true);
    });
  }, [enqueueSnackbar, initializeChat, activeSessionId, currentUserId, t]);

  useEffect(() => {
    if (exploredExperiencesNotification) {
      const LazyDownloadReportDropdown = lazyWithPreload(
        () => import("src/experiences/experiencesDrawer/components/downloadReportDropdown/DownloadReportDropdown")
      );
      LazyDownloadReportDropdown.preload().then(() => {
        console.debug("DownloadReportDropdown preloaded");
      });
    }
  }, [exploredExperiencesNotification]);

  useEffect(() => {
    if (activeSessionId && currentPhase.phase !== ConversationPhase.INITIALIZING) {
      fetchExperiences().then();
    }
  }, [activeSessionId, fetchExperiences, currentPhase.phase]);

  return (
    <Suspense fallback={<Backdrop isShown={true} transparent={true} />}>
      <ChatProvider
        handleOpenExperiencesDrawer={openExperiencesDrawer}
        removeMessageFromChat={removeMessageFromChat}
        addMessageToChat={addMessageToChat}
      >
        {/* The "is-initialized" attribute helps make the component testable.
            When the component mounts, an initialization function runs, changing the state and causing a rerender.
            Tests need to wait for the component to "settle" after mounting, but they don't know when that happens.
            To check if the component is settled, tests can wait for the "is-initialized" attribute to be true:
              await waitFor(() => {
                expect(screen.getByTestId(DATA_TEST_ID.CHAT_CONTAINER)).toHaveAttribute("is-initialized", "true");
              });
            This technique can solve the "Warning: An update to Chat inside a test was not wrapped in act(...)" warning. */}
        <Box
          data-testid={DATA_TEST_ID.CHAT_CONTAINER}
          is-initialized={`${initialized}`}
          sx={{ width: "100%", height: "100%", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}
        >
          <ChatPage
            aboveChatView={
              <ChatHeader
                experiencesExplored={exploredExperiencesCount.length}
                exploredExperiencesNotification={exploredExperiencesNotification}
                setExploredExperiencesNotification={setExploredExperiencesNotification}
                conversationCompleted={conversationCompleted}
                timeUntilNotification={timeUntilFeedbackNotification}
                progressPercentage={currentPhase.percentage}
              />
            }
            chatViewProps={{
              messages,
              quickReplyOptions,
              onQuickReplyClick: handleQuickReply,
              messageFieldProps: {
                handleSend,
                aiIsTyping,
                isChatFinished: conversationCompleted,
                isUploadingCv: isUploadingCv || activeUploadCount > 0,
                onUploadCv: handleUploadCv,
                currentPhase: currentPhase.phase,
                prefillMessage,
                failedSendDraft,
                cvUploadError,
                fillColor: theme.palette.secondary.main,
                isInputDisabled: isAwaitingBWSResponse,
                placeholderKey: isAwaitingBWSResponse ? "chat.chatMessageField.placeholders.bws" : undefined,
              },
              children: showBackdrop ? <InactiveBackdrop isShown={showBackdrop} /> : undefined,
            }}
            belowChatView={
              conversationCompleted && nextModule ? (
                <ModuleHandoffBanner
                  nextModuleLabel={t(nextModule.labelKey as any)}
                  nextModuleRoute={nextModule.route}
                />
              ) : undefined
            }
            sidebar={<SkillsDiscoverySidebar currentPhase={currentPhase} refreshToken={sidebarRefreshToken} />}
          />
        </Box>

        {showRefreshDialog && (
          <ConfirmModalDialog
            isOpen={showRefreshDialog}
            title={t("chat.chat.refreshConfirmationDialog.title")}
            content={
              <>
                {t("chat.chat.refreshConfirmationDialog.content", { appName })}
                <br />
                <br />
                {t("chat.chat.refreshConfirmationDialog.question", { appName })}
              </>
            }
            onCancel={cancelRefresh}
            onConfirm={confirmRefresh}
            onDismiss={cancelRefresh}
            cancelButtonText={t("chat.chat.refreshConfirmationDialog.waitButton", { appName })}
            confirmButtonText={t("chat.chat.refreshConfirmationDialog.refreshButton")}
          />
        )}

        {newSessionEnabled && newConversationDialog && (
          <ConfirmModalDialog
            isOpen={newConversationDialog}
            title={t("chat.chat.startNewConversationDialog.title")}
            content={
              <>
                {t("chat.chat.startNewConversationDialog.content")}
                <br />
                <br />
                {t("chat.chat.startNewConversationDialog.confirmation")}
              </>
            }
            onCancel={() => setNewConversationDialog(false)}
            onConfirm={handleConfirmNewConversation}
            onDismiss={() => setNewConversationDialog(false)}
            cancelButtonText={t("common.buttons.cancel")}
            confirmButtonText={t("common.buttons.confirm")}
          />
        )}
      </ChatProvider>
    </Suspense>
  );
};

export default Chat;
