/** Why a message could not be read aloud. */
export type TextToSpeechErrorKind =
  /** The device is offline, or the request did not reach the backend. */
  | "network"
  /** The user asked for too many messages to be read in a short time. */
  | "rateLimited"
  /** The text-to-speech service failed, or produced no audio. */
  | "unavailable"
  /** The browser did not let the audio play. */
  | "autoplayBlocked"
  /** Anything else. */
  | "unknown";

/** The state of the one read aloud player of the chat. */
export type PlaybackState =
  | { status: "idle" }
  | { status: "loading"; messageId: string }
  | { status: "playing"; messageId: string }
  | { status: "error"; messageId: string; error: TextToSpeechErrorKind };

/** The body of POST /text-to-speech/synthesize. */
export interface SynthesizeRequest {
  /** The plain text to read aloud. */
  text: string;
  /** The locale of the text, e.g. "en-US". */
  locale: string;
}
