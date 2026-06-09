import type { IChatMessage } from "src/chat/Chat.types";
import { generateAgentMessage, generateUserMessage } from "src/chat/util";
import type { CareerExplorerMessage } from "src/careerExplorer/types";
import type { AgentChatMessageProps } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";

export const mapCareerExplorerMessageToChatMessage = (
  msg: CareerExplorerMessage,
  isLastMessage: boolean = false,
  fillColor: string,
  textColor: string,
  onQuickReplyClick?: (label: string) => void
): IChatMessage<AgentChatMessageProps> | ReturnType<typeof generateUserMessage> => {
  if (msg.sender === "USER") {
    return generateUserMessage(msg.message, msg.sent_at, fillColor, textColor, msg.message_id);
  }
  const quickReplyOptions = isLastMessage ? msg.metadata?.quick_reply_options ?? null : null;
  return generateAgentMessage(
    msg.message_id,
    msg.message,
    msg.sent_at,
    null,
    quickReplyOptions,
    quickReplyOptions ? onQuickReplyClick : undefined
  );
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
