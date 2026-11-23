/**
 * Fakes of the browser APIs voice input uses (getUserMedia, MediaRecorder, AudioContext), which jsdom does not have.
 * Call `installMediaRecorderMock()` in a test (or beforeEach) and `uninstallMediaRecorderMock()` after it.
 */

export class FakeMediaStreamTrack {
  stopped = false;
  stop = jest.fn(() => {
    this.stopped = true;
  });
}

export class FakeMediaStream {
  readonly tracks = [new FakeMediaStreamTrack()];
  getTracks = () => this.tracks;
}

export class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  static supportedMimeTypes = ["audio/webm;codecs=opus", "audio/webm"];
  static isTypeSupported = jest.fn((mimeType: string) => FakeMediaRecorder.supportedMimeTypes.includes(mimeType));

  state: "inactive" | "recording" = "inactive";
  readonly mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  /** What the recorder gives when it stops. */
  recordedChunks: Blob[] = [new Blob(["recorded-audio"], { type: "audio/webm" })];

  constructor(
    readonly stream: FakeMediaStream,
    options?: { mimeType?: string }
  ) {
    this.mimeType = options?.mimeType ?? "";
    FakeMediaRecorder.instances.push(this);
  }

  start = jest.fn(() => {
    this.state = "recording";
  });

  stop = jest.fn(() => {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.recordedChunks.forEach((data) => this.ondataavailable?.({ data }));
    this.onstop?.();
  });
}

export class FakeAnalyserNode {
  fftSize = 512;
  /** The waveform the analyser reads: 128 is silence, 0 and 255 are the loudest. */
  static waveformValue = 128;
  getByteTimeDomainData = jest.fn((samples: Uint8Array) => samples.fill(FakeAnalyserNode.waveformValue));
}

export class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  closed = false;
  constructor() {
    FakeAudioContext.instances.push(this);
  }
  createAnalyser = jest.fn(() => new FakeAnalyserNode());
  createMediaStreamSource = jest.fn(() => ({ connect: jest.fn() }));
  close = jest.fn(() => {
    this.closed = true;
    return Promise.resolve();
  });
}

export interface MediaRecorderMock {
  getUserMedia: jest.Mock;
  streams: FakeMediaStream[];
}

const originals: { mediaDevices?: unknown; MediaRecorder?: unknown; AudioContext?: unknown } = {};

export const installMediaRecorderMock = (): MediaRecorderMock => {
  FakeMediaRecorder.instances = [];
  FakeMediaRecorder.supportedMimeTypes = ["audio/webm;codecs=opus", "audio/webm"];
  FakeAudioContext.instances = [];
  FakeAnalyserNode.waveformValue = 128;
  const streams: FakeMediaStream[] = [];
  const getUserMedia = jest.fn(async () => {
    const stream = new FakeMediaStream();
    streams.push(stream);
    return stream;
  });
  originals.mediaDevices = navigator.mediaDevices;
  originals.MediaRecorder = window.MediaRecorder;
  originals.AudioContext = window.AudioContext;
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true, writable: true });
  Object.defineProperty(window, "MediaRecorder", { value: FakeMediaRecorder, configurable: true, writable: true });
  Object.defineProperty(window, "AudioContext", { value: FakeAudioContext, configurable: true, writable: true });
  return { getUserMedia, streams };
};

export const uninstallMediaRecorderMock = () => {
  Object.defineProperty(navigator, "mediaDevices", {
    value: originals.mediaDevices,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "MediaRecorder", {
    value: originals.MediaRecorder,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "AudioContext", { value: originals.AudioContext, configurable: true, writable: true });
};
