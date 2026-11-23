/** Why voice input failed. */
export type SpeechToTextErrorKind =
  /** The user, or the browser, refused access to the microphone. */
  | "permissionDenied"
  /** There is no microphone. */
  | "noMicrophone"
  /** No speech was recognized in the recording. */
  | "noSpeech"
  /** The user transcribed too many recordings in a short time. */
  | "rateLimited"
  /** The speech-to-text service failed. */
  | "unavailable"
  /** The device is offline, or the request did not reach the backend. */
  | "network"
  /** Anything else. */
  | "unknown";

/** The state of voice input in the message field. */
export type RecordingState =
  | { status: "idle" }
  | { status: "recording"; startedAt: number }
  | { status: "transcribing" }
  | { status: "error"; error: SpeechToTextErrorKind };

/** The response of POST /speech-to-text/transcribe. */
export interface TranscriptionResponse {
  /** The transcript of the recording. */
  text: string;
  /** The locale the recording was transcribed in. */
  locale: string;
}
