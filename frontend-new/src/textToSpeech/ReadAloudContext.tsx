import React, { createContext, useContext, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getSpeechConfig } from "src/envService";
import { useSnackbar } from "src/theme/SnackbarProvider/SnackbarProvider";
import { useTextToSpeech, UseTextToSpeech } from "src/textToSpeech/useTextToSpeech";
import { TextToSpeechErrorKind } from "src/textToSpeech/textToSpeech.types";

/** The read aloud player of the chat, or null when read aloud is not offered. Provided by ReadAloudProvider. */
export const ReadAloudContext = createContext<UseTextToSpeech | null>(null);

const errorMessageKey = (error: TextToSpeechErrorKind) => {
  switch (error) {
    case "network":
      return "chat.readAloud.errors.network";
    case "rateLimited":
      return "chat.readAloud.errors.rateLimited";
    case "unavailable":
      return "chat.readAloud.errors.unavailable";
    case "autoplayBlocked":
      return "chat.readAloud.errors.autoplayBlocked";
    case "unknown":
      return "chat.readAloud.errors.unknown";
    default: {
      const unexpected: never = error;
      return unexpected;
    }
  }
};

/** Whether read aloud is offered in the locale: the deployment enables it, and for that locale. */
export const isReadAloudAvailable = (locale: string): boolean => {
  const { textToSpeech } = getSpeechConfig();
  return textToSpeech.enabled && textToSpeech.locales.includes(locale);
};

/**
 * Gives the messages of a chat one read aloud player, when read aloud is offered in the current locale.
 * Otherwise, the messages have no read aloud button.
 */
export const ReadAloudProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t, i18n } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const locale = i18n.language;
  const available = useMemo(() => isReadAloudAvailable(locale), [locale]);
  const player = useTextToSpeech({
    locale,
    maxTextBytes: getSpeechConfig().textToSpeech.maxTextBytes,
    onError: (error) => enqueueSnackbar(t(errorMessageKey(error)), { variant: "error" }),
  });
  const { stop } = player;

  // switching the locale stops the message being read, so it is never read in the voice of another locale
  useEffect(() => stop, [locale, stop]);

  const value = available ? player : null;
  return <ReadAloudContext.Provider value={value}>{children}</ReadAloudContext.Provider>;
};

/** The read aloud player of the chat, or null when read aloud is not offered. */
export const useReadAloud = (): UseTextToSpeech | null => useContext(ReadAloudContext);
