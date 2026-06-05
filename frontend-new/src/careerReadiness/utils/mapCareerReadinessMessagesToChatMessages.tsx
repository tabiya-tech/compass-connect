/**
 * Maps Career Readiness API messages to the chat UI format (IChatMessage).
 * Converts backend payloads into the shape ChatList expects and wires agent
 * messages to CareerReadinessAgentMessage so the first message can explain the module.
 */
import React from "react";
import type { IChatMessage } from "src/chat/Chat.types";
import { ConversationMessageSender } from "src/chat/ChatService/ChatService.types";
import type { CareerReadinessMessage } from "src/careerReadiness/types";
import CareerReadinessAgentMessage, {
  CAREER_READINESS_AGENT_MESSAGE_TYPE,
  type CareerReadinessAgentMessageProps,
} from "src/careerReadiness/components/CareerReadinessAgentMessage/CareerReadinessAgentMessage";
import CareerReadinessUserMessage, {
  CAREER_READINESS_USER_MESSAGE_TYPE,
  type CareerReadinessUserMessageProps,
} from "src/careerReadiness/components/CareerReadinessUserMessage/CareerReadinessUserMessage";

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
): IChatMessage<CareerReadinessAgentMessageProps> | IChatMessage<CareerReadinessUserMessageProps> => {
  const sentAt = msg.sent_at;
  if (msg.sender === "USER") {
    const payload: CareerReadinessUserMessageProps = {
      message: msg.message,
      fillColor,
      textColor,
    };
    return {
      type: CAREER_READINESS_USER_MESSAGE_TYPE,
      message_id: msg.message_id,
      sender: ConversationMessageSender.USER,
      payload,
      component: (p: CareerReadinessUserMessageProps) => <CareerReadinessUserMessage {...p} />,
    };
  }
  const quickReplyOptions = isLastMessage ? msg.metadata?.quick_reply_options ?? null : null;
  const payload: CareerReadinessAgentMessageProps = {
    message_id: msg.message_id,
    message: msg.message,
    sent_at: sentAt,
    quick_reply_options: quickReplyOptions,
    onQuickReplyClick: quickReplyOptions ? onQuickReplyClick : undefined,
  };
  return {
    type: CAREER_READINESS_AGENT_MESSAGE_TYPE,
    message_id: msg.message_id,
    sender: ConversationMessageSender.COMPASS,
    payload,
    component: (p: CareerReadinessAgentMessageProps) => <CareerReadinessAgentMessage {...p} />,
  };
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
