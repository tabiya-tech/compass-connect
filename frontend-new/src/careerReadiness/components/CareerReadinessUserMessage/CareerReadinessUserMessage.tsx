import React from "react";
import { Box, styled } from "@mui/material";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import ChatBubble from "src/chat/chatMessage/components/chatBubble/ChatBubble";

const uniqueId = "58df8006-bf2a-4d64-89d0-4442f262b702";

export const DATA_TEST_ID = {
  CAREER_READINESS_USER_MESSAGE_CONTAINER: `career-readiness-user-message-container-${uniqueId}`,
};

export const CAREER_READINESS_USER_MESSAGE_TYPE = `career-readiness-user-message-${uniqueId}`;

export interface CareerReadinessUserMessageProps {
  message: string;
  fillColor: string;
  textColor?: string;
}

const MessageContainer = styled(Box)<{ origin: ConversationMessageSender }>(({ theme, origin }) => ({
  display: "flex",
  flexDirection: "column",
  alignItems: origin === ConversationMessageSender.USER ? "flex-end" : "flex-start",
  marginBottom: theme.spacing(theme.tabiyaSpacing.sm),
  width: "100%",
}));

const CareerReadinessUserMessage: React.FC<CareerReadinessUserMessageProps> = ({ message, fillColor, textColor }) => {
  return (
    <MessageContainer
      origin={ConversationMessageSender.USER}
      data-testid={DATA_TEST_ID.CAREER_READINESS_USER_MESSAGE_CONTAINER}
    >
      <Box
        sx={{
          maxWidth: "80%",
          minWidth: "30%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <ChatBubble message={message} sender={ConversationMessageSender.USER} fillColor={fillColor} textColor={textColor} />
      </Box>
    </MessageContainer>
  );
};

export default CareerReadinessUserMessage;
