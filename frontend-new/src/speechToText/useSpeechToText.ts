import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StatusCodes } from "http-status-codes";
import { RestAPIError } from "src/error/restAPIError/RestAPIError";
import ErrorConstants from "src/error/restAPIError/RestAPIError.constants";
import SpeechToTextService from "src/speechToText/SpeechToTextService";
import { RecordingState, SpeechToTextErrorKind } from "src/speechToText/speechToText.types";

/** How many levels are kept for the graph: enough to fill a wide message field (it shows as many as fit). */
export const LEVEL_BARS = 160;
/** How often a new bar is added to the level graph, in milliseconds. */
export const LEVEL_SAMPLE_INTERVAL_MS = 100;

/** The recording formats, best first: Chrome and Firefox record Opus in WebM, Safari AAC in MP4. */
const PREFERRED_MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

// Safari before 14.1 only has the prefixed AudioContext, which the DOM typings do not declare
type WindowWithWebkitAudioContext = Window & { webkitAudioContext?: typeof AudioContext };

/** Whether the browser can record the microphone. */
export const isVoiceInputSupported = (): boolean =>
  typeof navigator !== "undefined" &&
  typeof navigator.mediaDevices?.getUserMedia === "function" &&
  typeof window.MediaRecorder !== "undefined";

const bestSupportedMimeType = (): string | undefined =>
  PREFERRED_MIME_TYPES.find((mimeType) => MediaRecorder.isTypeSupported?.(mimeType));

export const toSpeechToTextErrorKind = (error: unknown): SpeechToTextErrorKind => {
  // getUserMedia rejects with a DOMException named after the reason
  const name = error instanceof Error || error instanceof DOMException ? error.name : undefined;
  if (name === "NotAllowedError" || name === "SecurityError") return "permissionDenied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "noMicrophone";
  if (typeof navigator !== "undefined" && !navigator.onLine) return "network";
  if (error instanceof RestAPIError) {
    if (error.statusCode === StatusCodes.UNPROCESSABLE_ENTITY) return "noSpeech";
    if (error.statusCode === StatusCodes.TOO_MANY_REQUESTS) return "rateLimited";
    if (
      error.statusCode === StatusCodes.BAD_GATEWAY ||
      error.statusCode === StatusCodes.SERVICE_UNAVAILABLE ||
      error.statusCode === StatusCodes.GATEWAY_TIMEOUT
    ) {
      return "unavailable";
    }
    if (error.errorCode === ErrorConstants.ErrorCodes.FAILED_TO_FETCH) return "network";
  }
  return "unknown";
};

export interface UseSpeechToTextOptions {
  /** The locale the user speaks in. */
  locale: string;
  /** The longest recording, in seconds. The recording stops by itself when it is reached. */
  maxRecordingSeconds: number;
  /** Called with the transcript of a recording. */
  onTranscript: (text: string) => void;
  /** Called when voice input failed. */
  onError?: (error: SpeechToTextErrorKind) => void;
}

export interface UseSpeechToText {
  state: RecordingState;
  /** The latest audio levels, oldest first, each from 0 (silence) to 1. Empty when not recording. */
  levels: number[];
  /** Asks for the microphone, if needed, and starts recording. Does nothing if voice input is busy. */
  start: () => void;
  /** Stops recording and transcribes the recording, once. */
  stop: () => void;
  /** Stops recording, or transcribing, and drops the recording. */
  cancel: () => void;
}

/** What one recording holds on to. Releasing it stops the microphone and the level graph. */
interface Recording {
  stream: MediaStream;
  recorder: MediaRecorder;
  chunks: Blob[];
  audioContext?: AudioContext;
  animationFrame?: number;
  autoStopTimer?: ReturnType<typeof setTimeout>;
  cancelled: boolean;
}

/** The root mean square of the waveform: 0 for silence, about 1 for the loudest sound. */
const levelOf = (samples: Uint8Array): number => {
  let sum = 0;
  for (const sample of samples) {
    const centered = (sample - 128) / 128;
    sum += centered * centered;
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * 3);
};

/**
 * Voice input, as a voice note: the user records, then the recording is transcribed in one request.
 * While recording, the audio levels of the microphone are sampled locally for the level graph; nothing is sent.
 */
export const useSpeechToText = ({
  locale,
  maxRecordingSeconds,
  onTranscript,
  onError,
}: UseSpeechToTextOptions): UseSpeechToText => {
  const [state, setState] = useState<RecordingState>({ status: "idle" });
  const [levels, setLevels] = useState<number[]>([]);
  const recordingRef = useRef<Recording | null>(null);
  const startingRef = useRef(false);
  /** Identifies the latest request for the microphone: a request that is no longer the latest one is dropped. */
  const acquisitionRef = useRef(0);
  const transcriptionRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const callbacksRef = useRef({ onTranscript, onError });
  callbacksRef.current = { onTranscript, onError };

  const fail = useCallback((error: SpeechToTextErrorKind) => {
    if (!mountedRef.current) return;
    setState({ status: "error", error });
    callbacksRef.current.onError?.(error);
  }, []);

  const release = useCallback((recording: Recording) => {
    if (recording.animationFrame !== undefined) cancelAnimationFrame(recording.animationFrame);
    if (recording.autoStopTimer !== undefined) clearTimeout(recording.autoStopTimer);
    recording.stream.getTracks().forEach((track) => track.stop());
    recording.audioContext?.close().catch(() => {});
    recording.audioContext = undefined;
    if (recordingRef.current === recording) recordingRef.current = null;
    if (mountedRef.current) setLevels([]);
  }, []);

  const transcribe = useCallback(
    (recordingBlob: Blob) => {
      const controller = new AbortController();
      transcriptionRef.current = controller;
      setState({ status: "transcribing" });
      SpeechToTextService.getInstance()
        .transcribe(recordingBlob, locale, controller.signal)
        .then((response) => {
          if (controller.signal.aborted || !mountedRef.current) return;
          setState({ status: "idle" });
          callbacksRef.current.onTranscript(response.text);
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          console.warn("The recording could not be transcribed", e);
          fail(toSpeechToTextErrorKind(e));
        })
        .finally(() => {
          if (transcriptionRef.current === controller) transcriptionRef.current = null;
        });
    },
    [fail, locale]
  );

  const sampleLevels = useCallback((recording: Recording, analyser: AnalyserNode) => {
    const samples = new Uint8Array(analyser.fftSize);
    let lastSampleAt = 0;
    const onFrame = (now: number) => {
      if (recordingRef.current !== recording) return;
      if (now - lastSampleAt >= LEVEL_SAMPLE_INTERVAL_MS) {
        lastSampleAt = now;
        analyser.getByteTimeDomainData(samples);
        const level = levelOf(samples);
        setLevels((previous) => [...previous, level].slice(-LEVEL_BARS));
      }
      recording.animationFrame = requestAnimationFrame(onFrame);
    };
    recording.animationFrame = requestAnimationFrame(onFrame);
  }, []);

  const stop = useCallback(() => {
    const recording = recordingRef.current;
    if (!recording || recording.recorder.state === "inactive") return;
    recording.recorder.stop();
  }, []);

  const start = useCallback(() => {
    if (startingRef.current || recordingRef.current || transcriptionRef.current) return;
    startingRef.current = true;
    const acquisition = ++acquisitionRef.current;
    const isCurrent = () => acquisition === acquisitionRef.current && mountedRef.current;

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        if (!isCurrent()) {
          // cancelled, or unmounted, while the browser was asking for the microphone
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        startingRef.current = false;
        const mimeType = bestSupportedMimeType();
        let recorder: MediaRecorder;
        try {
          recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        } catch (e) {
          stream.getTracks().forEach((track) => track.stop());
          console.warn("The microphone cannot be recorded", e);
          fail(toSpeechToTextErrorKind(e));
          return;
        }
        const recording: Recording = { stream, recorder, chunks: [], cancelled: false };
        recordingRef.current = recording;

        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data.size > 0) recording.chunks.push(event.data);
        };
        recorder.onstop = () => {
          release(recording);
          if (recording.cancelled || !mountedRef.current) return;
          const recordingBlob = new Blob(recording.chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
          if (recordingBlob.size === 0) {
            fail("noSpeech");
            return;
          }
          transcribe(recordingBlob);
        };
        recorder.onerror = () => {
          recording.cancelled = true;
          release(recording);
          fail("unknown");
        };

        const AudioContextClass = window.AudioContext ?? (window as WindowWithWebkitAudioContext).webkitAudioContext;
        if (AudioContextClass) {
          try {
            recording.audioContext = new AudioContextClass();
            const analyser = recording.audioContext.createAnalyser();
            analyser.fftSize = 512;
            recording.audioContext.createMediaStreamSource(stream).connect(analyser);
            sampleLevels(recording, analyser);
          } catch (e) {
            // the level graph is a nicety: recording works without it
            console.warn("The audio levels cannot be shown", e);
          }
        }

        try {
          recorder.start();
        } catch (e) {
          // e.g. NotSupportedError: release the microphone and the level graph acquired so far
          recording.cancelled = true;
          release(recording);
          console.warn("The microphone cannot be recorded", e);
          fail(toSpeechToTextErrorKind(e));
          return;
        }
        recording.autoStopTimer = setTimeout(() => stop(), maxRecordingSeconds * 1000);
        setState({ status: "recording", startedAt: Date.now() });
      })
      .catch((e: unknown) => {
        if (!isCurrent()) return;
        startingRef.current = false;
        console.warn("The microphone cannot be used", e);
        fail(toSpeechToTextErrorKind(e));
      });
  }, [fail, maxRecordingSeconds, release, sampleLevels, stop, transcribe]);

  const cancel = useCallback(() => {
    // a request for the microphone still pending is dropped when it resolves
    acquisitionRef.current++;
    startingRef.current = false;
    transcriptionRef.current?.abort();
    transcriptionRef.current = null;
    const recording = recordingRef.current;
    if (recording) {
      recording.cancelled = true;
      if (recording.recorder.state !== "inactive") recording.recorder.stop();
      release(recording);
    }
    if (mountedRef.current) setState({ status: "idle" });
  }, [release]);

  // release the microphone and drop the recording when the field goes away
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      transcriptionRef.current?.abort();
      const recording = recordingRef.current;
      if (recording) {
        recording.cancelled = true;
        if (recording.recorder.state !== "inactive") recording.recorder.stop();
        release(recording);
      }
    };
  }, [release]);

  return useMemo(() => ({ state, levels, start, stop, cancel }), [state, levels, start, stop, cancel]);
};
