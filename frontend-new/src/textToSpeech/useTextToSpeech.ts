import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";

export type TextToSpeechStatus = "idle" | "loading" | "playing";

// Chrome pauses speechSynthesis after ~15 seconds; this workaround resumes it periodically
const CHROME_RESUME_INTERVAL_MS = 10000;

// Languages without common TTS voices — fall back to English
const LANGUAGE_FALLBACKS: Record<string, string> = {
  "ny-ZM": "en-US",
};

function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "") // fenced code blocks
    .replace(/\*\*(.*?)\*\*/g, "$1") // bold
    .replace(/\*(.*?)\*/g, "$1") // italic
    .replace(/#{1,6}\s/g, "") // headings
    .replace(/`(.*?)`/g, "$1") // inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // links
    .replace(/^>\s+/gm, "") // blockquotes
    .replace(/^[-*+]\s+/gm, "") // unordered list markers
    .replace(/^\d+\.\s+/gm, "") // ordered list markers
    .replace(/[_~]/g, ""); // underscores, strikethrough
}

export interface UseTextToSpeechReturn {
  status: TextToSpeechStatus;
  speak: (text: string) => void;
  stop: () => void;
  isSupported: boolean;
}

export function useTextToSpeech(): UseTextToSpeechReturn {
  const { i18n } = useTranslation();
  const [status, setStatus] = useState<TextToSpeechStatus>("idle");

  // Backend audio path refs
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // TODO: Remove browser speechSynthesis fallback once backend-only TTS is confirmed stable.
  // This fallback exists as a safety net during the transition from client-side to server-side TTS.
  // Browser fallback path refs
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const resumeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isBrowserTtsSupported = typeof window !== "undefined" && "speechSynthesis" in window;

  const cleanupBrowserFallback = useCallback(() => {
    if (resumeTimerRef.current) {
      clearInterval(resumeTimerRef.current);
      resumeTimerRef.current = null;
    }
    utteranceRef.current = null;
  }, []);

  const cleanupBackend = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanupBackend();
    // TODO: Remove browser speechSynthesis fallback
    if (isBrowserTtsSupported) {
      window.speechSynthesis.cancel();
    }
    cleanupBrowserFallback();
    setStatus("idle");
  }, [isBrowserTtsSupported, cleanupBrowserFallback, cleanupBackend]);

  // TODO: Remove browser speechSynthesis fallback once backend-only TTS is confirmed stable.
  const speakWithBrowserFallback = useCallback(
    (cleanText: string, language: string) => {
      if (!isBrowserTtsSupported) {
        setStatus("idle");
        return;
      }

      window.speechSynthesis.cancel();
      cleanupBrowserFallback();

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = language;
      utteranceRef.current = utterance;

      utterance.onend = () => {
        if (utteranceRef.current === utterance) {
          cleanupBrowserFallback();
          setStatus("idle");
        }
      };

      utterance.onerror = (event) => {
        if ((event as SpeechSynthesisErrorEvent).error === "interrupted") return;
        if (utteranceRef.current === utterance) {
          cleanupBrowserFallback();
          setStatus("idle");
        }
      };

      setStatus("playing");
      window.speechSynthesis.speak(utterance);

      // Chrome workaround: periodically pause/resume to prevent the 15-second cutoff
      resumeTimerRef.current = setInterval(() => {
        if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        }
      }, CHROME_RESUME_INTERVAL_MS);
    },
    [isBrowserTtsSupported, cleanupBrowserFallback]
  );

  const speak = useCallback(
    (text: string) => {
      // Stop any current playback (backend or browser)
      stop();

      const cleanText = stripMarkdown(text);
      if (!cleanText.trim()) return;

      const language = LANGUAGE_FALLBACKS[i18n.language] ?? i18n.language;
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setStatus("loading");

      const service = TextToSpeechService.getInstance();
      service
        .synthesize(cleanText, language)
        .then((audioUrl) => {
          if (controller.signal.aborted) return;

          const audio = new Audio(audioUrl);
          audioRef.current = audio;

          audio.onended = () => {
            if (audioRef.current === audio) {
              audioRef.current = null;
              setStatus("idle");
            }
          };
          audio.onerror = () => {
            if (audioRef.current === audio) {
              audioRef.current = null;
              setStatus("idle");
            }
          };

          setStatus("playing");
          audio.play().catch(() => {
            if (audioRef.current === audio) {
              audioRef.current = null;
              setStatus("idle");
            }
          });
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            // TODO: Remove browser speechSynthesis fallback once backend-only TTS is confirmed stable.
            // Backend failed — fall back to browser speechSynthesis
            speakWithBrowserFallback(cleanText, language);
          }
        });
    },
    [i18n.language, stop, speakWithBrowserFallback]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupBackend();
      if (isBrowserTtsSupported) {
        window.speechSynthesis.cancel();
      }
      cleanupBrowserFallback();
    };
  }, [isBrowserTtsSupported, cleanupBrowserFallback, cleanupBackend]);

  return { status, speak, stop, isSupported: true };
}
