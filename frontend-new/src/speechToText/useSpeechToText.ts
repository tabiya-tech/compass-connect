import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import SpeechToTextService from "src/speechToText/SpeechToTextService";

export type SpeechToTextStatus = "idle" | "recording" | "transcribing" | "error";

const MAX_DURATION_SECONDS = 60;

// Preferred MIME types for MediaRecorder, in order of preference
const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
  "video/webm",
  "video/mp4",
];

function getSupportedMimeType(): string {
  for (const mimeType of PREFERRED_MIME_TYPES) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }
  return "";
}

function getWebSpeechRecognition(): (new () => SpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null;
}

export interface UseSpeechToTextOptions {
  onTranscriptionComplete: (text: string) => void;
}

export interface UseSpeechToTextReturn {
  status: SpeechToTextStatus;
  interimText: string;
  error: string | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
  cancelRecording: () => void;
  elapsedSeconds: number;
  isSupported: boolean;
}

export function useSpeechToText({ onTranscriptionComplete }: UseSpeechToTextOptions): UseSpeechToTextReturn {
  const { t, i18n } = useTranslation();

  const [status, setStatus] = useState<SpeechToTextStatus>("idle");
  const [interimText, setInterimText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);
  const onTranscriptionCompleteRef = useRef(onTranscriptionComplete);

  // Keep the callback ref up to date
  useEffect(() => {
    onTranscriptionCompleteRef.current = onTranscriptionComplete;
  }, [onTranscriptionComplete]);

  const isSupported =
    typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

  const cleanup = useCallback(() => {
    // Stop timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    // Stop speech recognition
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    // Stop media recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    mediaRecorderRef.current = null;
    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    audioChunksRef.current = [];
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const startRecording = useCallback(async () => {
    if (status !== "idle" && status !== "error") return;

    setError(null);
    setInterimText("");
    setElapsedSeconds(0);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Set up MediaRecorder
      const mimeType = getSupportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.start();

      // Set up Web Speech API (if available)
      const SpeechRecognitionConstructor = getWebSpeechRecognition();
      if (SpeechRecognitionConstructor) {
        const recognition = new SpeechRecognitionConstructor();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = i18n.language;
        recognitionRef.current = recognition;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
          let transcript = "";
          for (let i = 0; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
          }
          setInterimText(transcript);
        };

        recognition.onerror = () => {
          // Web Speech API errors are non-fatal — we still have the audio recording
        };

        recognition.onend = () => {
          // Restart if still recording (browser may auto-stop after silence)
          if (mediaRecorderRef.current?.state === "recording" && recognitionRef.current) {
            try {
              recognitionRef.current.start();
            } catch {
              // ignore — may already be started
            }
          }
        };

        recognition.start();
      }

      // Start timer
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => {
          const next = prev + 1;
          if (next >= MAX_DURATION_SECONDS) {
            // Auto-stop will be triggered by the effect below
          }
          return next;
        });
      }, 1000);

      setStatus("recording");
    } catch (err) {
      cleanup();
      const isPermissionDenied =
        err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError");
      setError(
        isPermissionDenied
          ? t("chat.chatMessageField.voiceErrors.micPermissionDenied")
          : t("chat.chatMessageField.voiceErrors.transcriptionFailed")
      );
      setStatus("error");
    }
  }, [status, i18n.language, t, cleanup]);

  const stopRecording = useCallback(async () => {
    if (status !== "recording") return;

    cancelledRef.current = false;

    // Stop speech recognition
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }

    // Stop timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    setStatus("transcribing");

    // Stop media recorder and wait for the final data
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      setStatus("idle");
      setInterimText("");
      return;
    }

    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });

    // Check if cancelled during the await
    if (cancelledRef.current) {
      return;
    }

    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    const audioBlob = new Blob(audioChunksRef.current, {
      type: recorder.mimeType || "audio/webm",
    });
    audioChunksRef.current = [];
    mediaRecorderRef.current = null;

    if (audioBlob.size === 0) {
      setError(t("chat.chatMessageField.voiceErrors.transcriptionFailed"));
      setStatus("error");
      setInterimText("");
      return;
    }

    try {
      const service = SpeechToTextService.getInstance();
      const result = await service.transcribe(audioBlob, i18n.language);
      if (cancelledRef.current) return;
      // Guard against empty transcription from backend
      if (!result.text?.trim()) {
        setInterimText("");
        setStatus("idle");
        return;
      }
      onTranscriptionCompleteRef.current(result.text);
      setInterimText("");
      setStatus("idle");
    } catch {
      if (cancelledRef.current) return;
      setError(t("chat.chatMessageField.voiceErrors.transcriptionFailed"));
      setStatus("error");
      setInterimText("");
    }
  }, [status, i18n.language, t]);

  // Auto-stop at max duration
  useEffect(() => {
    if (status === "recording" && elapsedSeconds >= MAX_DURATION_SECONDS) {
      stopRecording();
    }
  }, [elapsedSeconds, status, stopRecording]);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    cleanup();
    setStatus("idle");
    setInterimText("");
    setElapsedSeconds(0);
    setError(null);
  }, [cleanup]);

  return {
    status,
    interimText,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
    elapsedSeconds,
    isSupported,
  };
}
