import React from "react";
import type { IChatMessage } from "src/chat/Chat.types";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import { generateUserMessage } from "src/chat/util";
import type { CareerExplorerMessage } from "src/careerExplorer/types";
import CareerExplorerAgentMessage, {
  CAREER_EXPLORER_AGENT_MESSAGE_TYPE,
  type CareerExplorerAgentMessageProps,
} from "src/careerExplorer/components/CareerExplorerAgentMessage/CareerExplorerAgentMessage";

export const mapCareerExplorerMessageToChatMessage = (
  msg: CareerExplorerMessage,
  isLastMessage: boolean = false,
  fillColor: string,
  textColor: string,
  onQuickReplyClick?: (label: string) => void
): IChatMessage<CareerExplorerAgentMessageProps> | ReturnType<typeof generateUserMessage> => {
  const sentAt = msg.sent_at;
  if (msg.sender === "USER") {
    return generateUserMessage(msg.message, sentAt, fillColor, textColor, msg.message_id);
  }
  const quickReplyOptions = isLastMessage ? msg.metadata?.quick_reply_options ?? null : null;
  const payload: CareerExplorerAgentMessageProps = {
    message_id: msg.message_id,
    message: msg.message,
    sent_at: sentAt,
    quick_reply_options: quickReplyOptions,
    onQuickReplyClick: quickReplyOptions ? onQuickReplyClick : undefined,
  };
  return {
    type: CAREER_EXPLORER_AGENT_MESSAGE_TYPE,
    message_id: msg.message_id,
    sender: ConversationMessageSender.COMPASS,
    payload,
    component: (p: CareerExplorerAgentMessageProps) => <CareerExplorerAgentMessage {...p} />,
  };
};

export const mapCareerExplorerMessagesToChatMessages = (
  messages: CareerExplorerMessage[],
  fillColor: string,
  textColor: string,
  onQuickReplyClick?: (label: string) => void
): IChatMessage<any>[] => {
  return messages.map((msg, idx) =>
    mapCareerExplorerMessageToChatMessage(msg, idx === messages.length - 1, fillColor, textColor, onQuickReplyClick)
  );
};
