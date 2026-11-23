import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StatusCodes } from "http-status-codes";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";
import TextToSpeechService from "src/textToSpeech/TextToSpeechService";
import { splitIntoParts, toPlainText } from "src/textToSpeech/plainText";
import { PlaybackState, TextToSpeechErrorKind } from "src/textToSpeech/textToSpeech.types";

export interface UseTextToSpeechOptions {
  /** The locale the messages are read in. */
  locale: string;
  /** The longest text read in one request, in bytes of UTF-8. Longer messages are read in parts. */
  maxTextBytes: number;
  /** Called when a message could not be read aloud. */
  onError?: (error: TextToSpeechErrorKind) => void;
}

export interface UseTextToSpeech {
  state: PlaybackState;
  /** Reads a message aloud, stopping the one being read. */
  play: (messageId: string, markdown: string) => void;
  /** Stops reading at once, including a message whose audio is still loading. */
  stop: () => void;
}

/** One message being read: aborting its controller stops it, wherever it is. */
interface Session {
  controller: AbortController;
  objectUrls: string[];
}

class AutoplayBlockedError extends Error {}

export const toTextToSpeechErrorKind = (error: unknown): TextToSpeechErrorKind => {
  if (error instanceof AutoplayBlockedError) return "autoplayBlocked";
  if (typeof navigator !== "undefined" && !navigator.onLine) return "network";
  if (error instanceof RestAPIError) {
    if (error.statusCode === StatusCodes.TOO_MANY_REQUESTS) return "rateLimited";
    if (
      error.statusCode === StatusCodes.BAD_GATEWAY ||
      error.statusCode === StatusCodes.SERVICE_UNAVAILABLE ||
      error.statusCode === StatusCodes.GATEWAY_TIMEOUT ||
      error.statusCode === StatusCodes.UNPROCESSABLE_ENTITY
    ) {
      return "unavailable";
    }
    if (error.errorCode === ErrorConstants.ErrorCodes.FAILED_TO_FETCH) return "network";
  }
  return "unknown";
};

/** Plays the audio until it ends. Resolves early, without error, when the session is aborted. */
const playToTheEnd = (audio: HTMLAudioElement, url: string, signal: AbortSignal): Promise<void> =>
  new Promise<void>((resolve, reject) => {
    const cleanUp = () => {
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
      signal.removeEventListener("abort", onAbort);
    };
    const onEnded = () => {
      cleanUp();
      resolve();
    };
    const onError = () => {
      cleanUp();
      reject(new Error("The audio could not be played"));
    };
    const onAbort = () => {
      cleanUp();
      resolve();
    };
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onError);
    signal.addEventListener("abort", onAbort);
    audio.src = url;
    audio.play().catch((e: unknown) => {
      cleanUp();
      if (signal.aborted) {
        resolve();
      } else if (e instanceof DOMException && e.name === "NotAllowedError") {
        reject(new AutoplayBlockedError(e.message));
      } else {
        reject(e);
      }
    });
  });

/**
 * The one read aloud player of a chat: playing a message stops the one before, and unmounting stops everything.
 * A message is turned into plain text, split into parts that fit in one request, and the parts are read in order,
 * the next one being fetched while the current one plays.
 */
export const useTextToSpeech = ({ locale, maxTextBytes, onError }: UseTextToSpeechOptions): UseTextToSpeech => {
  const [state, setState] = useState<PlaybackState>({ status: "idle" });
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const endSession = useCallback((session: Session) => {
    session.controller.abort();
    audioRef.current?.pause();
    audioRef.current?.removeAttribute("src");
    session.objectUrls.forEach((url) => URL.revokeObjectURL(url));
    session.objectUrls = [];
    if (sessionRef.current === session) {
      sessionRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    if (sessionRef.current) {
      endSession(sessionRef.current);
    }
    setState({ status: "idle" });
  }, [endSession]);

  const play = useCallback(
    (messageId: string, markdown: string) => {
      if (sessionRef.current) {
        endSession(sessionRef.current);
      }
      const parts = splitIntoParts(toPlainText(markdown), maxTextBytes);
      if (parts.length === 0) {
        setState({ status: "idle" });
        return;
      }
      const session: Session = { controller: new AbortController(), objectUrls: [] };
      sessionRef.current = session;
      const { signal } = session.controller;
      audioRef.current ??= new Audio();
      const audio = audioRef.current;
      setState({ status: "loading", messageId });

      const fetchPart = (index: number) => {
        const request = TextToSpeechService.getInstance().synthesize(parts[index], locale, signal);
        // a part fetched ahead may never be awaited, when the user stops first
        request.catch(() => {});
        return request;
      };

      const readAllParts = async () => {
        let nextPart = fetchPart(0);
        for (let index = 0; index < parts.length; index++) {
          const audioBlob = await nextPart;
          if (signal.aborted) return;
          if (index + 1 < parts.length) {
            nextPart = fetchPart(index + 1);
          }
          const url = URL.createObjectURL(audioBlob);
          session.objectUrls.push(url);
          const playing = playToTheEnd(audio, url, signal);
          setState({ status: "playing", messageId });
          await playing;
          URL.revokeObjectURL(url);
          session.objectUrls = session.objectUrls.filter((objectUrl) => objectUrl !== url);
          if (signal.aborted) return;
        }
      };

      readAllParts()
        .then(() => {
          if (sessionRef.current !== session) return;
          endSession(session);
          setState({ status: "idle" });
        })
        .catch((e: unknown) => {
          if (signal.aborted || sessionRef.current !== session) return;
          const error = toTextToSpeechErrorKind(e);
          console.warn("A message could not be read aloud", error, e);
          endSession(session);
          setState({ status: "error", messageId, error });
          onErrorRef.current?.(error);
        });
    },
    [endSession, locale, maxTextBytes]
  );

  // stop reading when the chat goes away (unmount, route change)
  useEffect(
    () => () => {
      if (sessionRef.current) {
        endSession(sessionRef.current);
      }
    },
    [endSession]
  );

  return useMemo(() => ({ state, play, stop }), [state, play, stop]);
};
