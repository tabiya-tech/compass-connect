import React from "react";
import { Box } from "@mui/material";
import { MessageContainer } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";
import ConversationConclusionFooter from "src/chat/chatMessage/conversationConclusionChatMessage/conversationConclusionFooter/ConversationConclusionFooter";
import ChatBubble from "src/chat/chatMessage/components/chatBubble/ChatBubble";
import BrandLogo from "src/chat/chatMessage/components/brandLogo/BrandLogo";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";

const uniqueId = "2fbaf2ef-9eab-485a-bd28-b4a164e18b06";

export const DATA_TEST_ID = {
  CONVERSATION_CONCLUSION_CHAT_MESSAGE_CONTAINER: `conversation_conclusion_chat-message-container-${uniqueId}`,
  CONVERSATION_CONCLUSION_CHAT_MESSAGE_BRAND_LOGO: `conversation_conclusion_chat-message-brand-logo-${uniqueId}`,
};

export const CONVERSATION_CONCLUSION_CHAT_MESSAGE_TYPE = `conversation-conclusion-message-${uniqueId}`;

export interface ConversationConclusionChatMessageProps {
  message: string;
}

const ConversationConclusionChatMessage: React.FC<ConversationConclusionChatMessageProps> = ({ message }) => {
  return (
    <MessageContainer
      origin={ConversationMessageSender.COMPASS}
      data-testid={DATA_TEST_ID.CONVERSATION_CONCLUSION_CHAT_MESSAGE_CONTAINER}
    >
      <Box data-testid={DATA_TEST_ID.CONVERSATION_CONCLUSION_CHAT_MESSAGE_BRAND_LOGO}>
        <BrandLogo />
      </Box>
      <ChatBubble message={message} sender={ConversationMessageSender.COMPASS}>
        <ConversationConclusionFooter />
      </ChatBubble>
    </MessageContainer>
  );
};

export default ConversationConclusionChatMessage;
