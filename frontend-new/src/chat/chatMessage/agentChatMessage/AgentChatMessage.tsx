import React from "react";
import { Box, styled } from "@mui/material";
import { ConversationMessageSender, MessageReaction, QuickReplyOption } from "src/chat/ChatService/ChatService.types";
import ChatBubble from "src/chat/chatMessage/components/chatBubble/ChatBubble";
import BrandLogo from "src/chat/chatMessage/components/brandLogo/BrandLogo";

const uniqueId = "2fbaf2ef-9eab-485a-bd28-b4a164e18b06";

export const DATA_TEST_ID = {
  CHAT_MESSAGE_CONTAINER: `chat-message-container-${uniqueId}`,
  CHAT_MESSAGE_BRAND_LOGO: `chat-message-brand-logo-${uniqueId}`,
};

export const MessageContainer = styled(Box)<{ origin: ConversationMessageSender }>(({ theme, origin }) => ({
  display: "flex",
  flexDirection: "row",
  justifyItems: "center",
  alignItems: origin === ConversationMessageSender.USER ? "flex-end" : "flex-start",
  width: "100%",
}));

export const AGENT_CHAT_MESSAGE_TYPE = `agent-message-${uniqueId}`;

export interface AgentChatMessageProps {
  message_id: string;
  message: string;
  sent_at: string; // ISO formatted datetime string
  reaction?: MessageReaction | null;
  quick_reply_options?: QuickReplyOption[] | null;
  onQuickReplyClick?: (label: string) => void;
}

const AgentChatMessage: React.FC<AgentChatMessageProps> = ({ message }) => {
  return (
    <MessageContainer origin={ConversationMessageSender.COMPASS} data-testid={DATA_TEST_ID.CHAT_MESSAGE_CONTAINER}>
      <Box data-testid={DATA_TEST_ID.CHAT_MESSAGE_BRAND_LOGO}>
        <BrandLogo />
      </Box>
      <Box
        sx={{
          width: "fit-content",
          minWidth: "30%",
          maxWidth: "80%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
        }}
      >
        <Box sx={{ width: "100%" }}>
          <ChatBubble message={message} sender={ConversationMessageSender.COMPASS} />
        </Box>
      </Box>
    </MessageContainer>
  );
};

export default AgentChatMessage;
