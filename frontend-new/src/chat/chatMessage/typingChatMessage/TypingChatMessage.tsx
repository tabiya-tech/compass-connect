import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Box, keyframes, Typography } from "@mui/material";
import ChatBubble from "src/chat/chatMessage/components/chatBubble/ChatBubble";
import BrandLogo from "src/chat/chatMessage/components/brandLogo/BrandLogo";
import { MessageContainer } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import { AnimatePresence, motion } from "framer-motion";

const uniqueId = "eb14a7aa-b515-4ab9-9829-8110346d9090";

export const DATA_TEST_ID = {
  TYPING_CHAT_MESSAGE_CONTAINER: `typing-chat-message-container-${uniqueId}`,
  TYPING_CHAT_MESSAGE_BRAND_LOGO: `typing-chat-message-brand-logo-${uniqueId}`,
  TYPING_CHAT_MESSAGE_DOT: `typing-chat-message-dot-${uniqueId}`,
};

export const UI_TEXT_KEYS = {
  // i18n keys
  TYPING: "chat.chatMessage.typingChatMessage.typing",
  THINKING: "chat.chatMessage.typingChatMessage.thinking",
  STILL_WORKING: "chat.chatMessage.typingChatMessage.stillWorking",
  THANKS_FOR_WAITING: "chat.chatMessage.typingChatMessage.thanksForWaiting",
} as const;

/**
 * How long to wait before the text changes from "typing" to "thinking".
 * Kept short so the user sees the app is still working early on; replies often take several seconds.
 */
export const WAIT_BEFORE_THINKING = 4000;

/**
 * How long after the "thinking" text appears to show the following stages.
 * Long waits get a reassuring message, so the user doesn't think the app is stuck.
 */
export const WAIT_BEFORE_STILL_WORKING = 8000;
export const WAIT_BEFORE_THANKS_FOR_WAITING = 21000;

export const TYPING_CHAT_MESSAGE_TYPE = `typing-message-${uniqueId}`;

export interface TypingChatMessageProps {
  /** Milliseconds before the "thinking" text replaces the "typing" text. The later stages follow from this point. */
  waitBeforeThinking?: number;
  /** Optional text for the "thinking" stage, e.g. a phase-specific message. */
  thinkingMessage?: string;
}

const bounceAnimation = keyframes`
    0%, 80%, 100% {
        transform: translateY(0);
        opacity: 0.4;
    }
    40% {
        transform: translateY(-5px);
        opacity: 1;
    }
`;

const textPulseAnimation = keyframes`
    0%, 100% {
        opacity: 0.6;
    }
    50% {
        opacity: 1;
    }
`;

const textVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

const DOT_SIZE = "8px";

const TypingChatMessage: React.FC<TypingChatMessageProps> = ({
  waitBeforeThinking = WAIT_BEFORE_THINKING,
  thinkingMessage,
}) => {
  const { t } = useTranslation();
  const [displayText, setDisplayText] = useState(t(UI_TEXT_KEYS.TYPING));

  useEffect(() => {
    // Move through the stages while the user waits, so the message keeps changing on long waits.
    const stages: { delay: number; text: string }[] = [
      { delay: waitBeforeThinking, text: thinkingMessage ?? t(UI_TEXT_KEYS.THINKING) },
      { delay: waitBeforeThinking + WAIT_BEFORE_STILL_WORKING, text: t(UI_TEXT_KEYS.STILL_WORKING) },
      { delay: waitBeforeThinking + WAIT_BEFORE_THANKS_FOR_WAITING, text: t(UI_TEXT_KEYS.THANKS_FOR_WAITING) },
    ];
    const timers = stages.map(({ delay, text }) => setTimeout(() => setDisplayText(text), delay));

    return () => {
      timers.forEach(clearTimeout);
    };
  }, [waitBeforeThinking, t, thinkingMessage]);

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={displayText}
        initial="hidden"
        animate="visible"
        exit="hidden"
        variants={textVariants}
        transition={{ duration: 0.3 }}
      >
        <MessageContainer
          origin={ConversationMessageSender.COMPASS}
          data-testid={DATA_TEST_ID.TYPING_CHAT_MESSAGE_CONTAINER}
        >
          <Box data-testid={DATA_TEST_ID.TYPING_CHAT_MESSAGE_BRAND_LOGO}>
            <BrandLogo />
          </Box>
          <ChatBubble message="" sender={ConversationMessageSender.COMPASS}>
            {/* role="status" makes screen readers announce each stage as the text changes */}
            <Box display="flex" alignItems="center" gap={1.5} role="status" aria-live="polite">
              <Box display="flex" alignItems="center" gap={0.5} aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <Box
                    key={i}
                    component="span"
                    data-testid={DATA_TEST_ID.TYPING_CHAT_MESSAGE_DOT}
                    sx={{
                      display: "inline-block",
                      width: DOT_SIZE,
                      height: DOT_SIZE,
                      borderRadius: "50%",
                      backgroundColor: "primary.main",
                      animation: `${bounceAnimation} 1.2s infinite ease-in-out`,
                      animationDelay: `${i * 0.15}s`,
                      "@media (prefers-reduced-motion: reduce)": {
                        animation: "none",
                        opacity: 0.7,
                      },
                    }}
                  />
                ))}
              </Box>
              <Typography
                sx={{
                  color: "text.secondary",
                  animation: `${textPulseAnimation} 2s infinite ease-in-out`,
                  "@media (prefers-reduced-motion: reduce)": {
                    animation: "none",
                  },
                }}
              >
                {displayText}
              </Typography>
            </Box>
          </ChatBubble>
        </MessageContainer>
      </motion.div>
    </AnimatePresence>
  );
};

export default TypingChatMessage;
