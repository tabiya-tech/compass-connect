/**
 * Maps Career Readiness API messages to the chat UI format (IChatMessage).
 * Converts backend payloads into the shape ChatList expects and wires agent
 * messages to AgentChatMessage so the first message can explain the module.
 */
import type { IChatMessage } from "src/chat/Chat.types";
import type { CareerReadinessMessage } from "src/careerReadiness/types";
import { generateAgentMessage, generateUserMessage } from "src/chat/util";
import type { AgentChatMessageProps } from "src/chat/chatMessage/agentChatMessage/AgentChatMessage";
import type { UserChatMessageProps } from "src/chat/chatMessage/userChatMessage/UserChatMessage";

export const isBackendQuizAnswersMessage = (msg: CareerReadinessMessage): boolean => {
  return msg.sender === "USER" && msg.message.startsWith("Quiz answers:");
};

export const isBackendQuizScoreMessage = (msg: CareerReadinessMessage): boolean => {
  return msg.sender === "AGENT" && /^You scored \d+\/\d+\./.test(msg.message);
};

export const isBackendPassedQuizScoreMessage = (msg: CareerReadinessMessage): boolean => {
  return isBackendQuizScoreMessage(msg) && msg.message.includes("Congratulations, you passed!");
};

export const isBackendFailedQuizScoreMessage = (msg: CareerReadinessMessage): boolean => {
  return isBackendQuizScoreMessage(msg) && !isBackendPassedQuizScoreMessage(msg);
};

export const isHiddenCareerReadinessSystemMessage = (
  msg: CareerReadinessMessage,
  index: number,
  messages: CareerReadinessMessage[]
): boolean => {
  if (isBackendQuizScoreMessage(msg)) {
    return true;
  }

  if (isBackendQuizAnswersMessage(msg)) {
    const nextQuizScoreMessage = messages.slice(index + 1).find(isBackendQuizScoreMessage);
    return Boolean(nextQuizScoreMessage);
  }

  return false;
};

export interface QuizHistorySummary {
  answersMessage?: string;
  answers?: Record<number, string>;
  feedbackMessage?: string;
  feedbackMessageId?: string;
  feedbackSentAt?: string;
  score?: number;
  total?: number;
  passed: boolean;
}

export const parseQuizAnswersMessage = (message: string): Record<number, string> => {
  const answersPart = message.replace(/^Quiz answers:\s*/, "");
  return answersPart
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce<Record<number, string>>((acc, part) => {
      const match = part.match(/^(\d+)\.([A-D])$/i);
      if (match) {
        acc[Number(match[1])] = match[2].toUpperCase();
      }
      return acc;
    }, {});
};

export const getLatestQuizHistorySummary = (messages: CareerReadinessMessage[]): QuizHistorySummary | null => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const scoreMessage = messages[i];
    if (!isBackendQuizScoreMessage(scoreMessage)) continue;

    const answersMessage = messages.slice(0, i).reverse().find(isBackendQuizAnswersMessage);
    const scoreMatch = scoreMessage.message.match(/^You scored (\d+)\/(\d+)\./);

    return {
      answersMessage: answersMessage?.message,
      answers: answersMessage ? parseQuizAnswersMessage(answersMessage.message) : undefined,
      feedbackMessage: scoreMessage.message,
      feedbackMessageId: scoreMessage.message_id,
      feedbackSentAt: scoreMessage.sent_at,
      score: scoreMatch ? Number(scoreMatch[1]) : undefined,
      total: scoreMatch ? Number(scoreMatch[2]) : undefined,
      passed: isBackendPassedQuizScoreMessage(scoreMessage),
    };
  }

  return null;
};

export const mapCareerReadinessMessageToChatMessage = (
  msg: CareerReadinessMessage,
  isLastMessage: boolean = false,
  fillColor: string,
  textColor?: string,
  onQuickReplyClick?: (label: string) => void
): IChatMessage<AgentChatMessageProps> | IChatMessage<UserChatMessageProps> => {
  if (msg.sender === "USER") {
    return generateUserMessage(msg.message, msg.sent_at, fillColor, textColor ?? "", msg.message_id);
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

export const mapCareerReadinessMessagesToChatMessages = (
  messages: CareerReadinessMessage[],
  fillColor: string,
  textColor: string,
  onQuickReplyClick?: (label: string) => void
): IChatMessage<any>[] => {
  const visible = messages.filter((msg, index) => !isHiddenCareerReadinessSystemMessage(msg, index, messages));
  return visible.map((msg, idx) =>
    mapCareerReadinessMessageToChatMessage(msg, idx === visible.length - 1, fillColor, textColor, onQuickReplyClick)
  );
};
