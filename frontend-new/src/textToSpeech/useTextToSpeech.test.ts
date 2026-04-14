// mute the console
import "src/_test_utilities/consoleMock";

import { renderHook, act, waitFor } from "src/_test_utilities/test-utils";
import { useTextToSpeech } from "./useTextToSpeech";

// --- Mocks ---

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: mockLanguage },
  }),
}));

let mockLanguage = "en-US";

const mockSynthesize = jest.fn();
jest.mock("src/textToSpeech/TextToSpeechService", () => ({
  __esModule: true,
  default: {
    getInstance: () => ({ synthesize: mockSynthesize }),
  },
}));

// Mock Audio
const mockPlay = jest.fn().mockResolvedValue(undefined);
const mockPause = jest.fn();
let mockAudioInstance: any;

// Mock speechSynthesis
const mockCancel = jest.fn();
const mockSpeak = jest.fn();

// Mock SpeechSynthesisUtterance (not available in jsdom)
(global as any).SpeechSynthesisUtterance = jest.fn().mockImplementation((text: string) => ({
  text,
  lang: "",
  onend: null as (() => void) | null,
  onerror: null as ((event: any) => void) | null,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockLanguage = "en-US";

  mockAudioInstance = {
    play: mockPlay,
    pause: mockPause,
    currentTime: 0,
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
  };
  global.Audio = jest.fn(() => mockAudioInstance) as any;

  Object.defineProperty(window, "speechSynthesis", {
    value: {
      cancel: mockCancel,
      speak: mockSpeak,
      speaking: false,
      paused: false,
      pause: jest.fn(),
      resume: jest.fn(),
    },
    writable: true,
    configurable: true,
  });
});

describe("useTextToSpeech", () => {
  test("should start with idle status and isSupported true", () => {
    // WHEN the hook is rendered
    const { result } = renderHook(() => useTextToSpeech());

    // THEN expect the initial status to be idle
    expect(result.current.status).toBe("idle");
    // AND expect isSupported to be true
    expect(result.current.isSupported).toBe(true);
  });

  test("should transition to loading then playing on successful backend synthesis", async () => {
    // GIVEN the backend synthesis resolves with an audio URL
    const givenAudioUrl = "blob:mock-audio-url";
    mockSynthesize.mockResolvedValue(givenAudioUrl);

    // WHEN the hook is rendered
    const { result } = renderHook(() => useTextToSpeech());

    // AND speak is called with a message
    act(() => {
      result.current.speak("Hello world");
    });

    // THEN expect the status to transition to playing after synthesis completes
    await waitFor(() => {
      expect(result.current.status).toBe("playing");
    });

    // AND expect the Audio constructor to have been called with the synthesized URL
    expect(global.Audio).toHaveBeenCalledWith(givenAudioUrl);
    // AND expect play to have been called on the audio element
    expect(mockPlay).toHaveBeenCalled();
  });

  test("should transition back to idle when audio ends", async () => {
    // GIVEN the backend synthesis resolves with an audio URL
    mockSynthesize.mockResolvedValue("blob:mock-audio-url");

    // WHEN the hook is rendered and speak is called
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Hello world");
    });

    // AND the audio starts playing
    await waitFor(() => {
      expect(result.current.status).toBe("playing");
    });

    // AND the audio ends
    act(() => {
      if (mockAudioInstance.onended) {
        mockAudioInstance.onended();
      }
    });

    // THEN expect the status to transition back to idle
    await waitFor(() => {
      expect(result.current.status).toBe("idle");
    });
  });

  test("should stop playback and return to idle when stop is called", async () => {
    // GIVEN the backend synthesis resolves and audio is playing
    mockSynthesize.mockResolvedValue("blob:mock-audio-url");

    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Hello world");
    });

    await waitFor(() => {
      expect(result.current.status).toBe("playing");
    });

    // WHEN stop is called
    act(() => {
      result.current.stop();
    });

    // THEN expect the status to return to idle
    expect(result.current.status).toBe("idle");
    // AND expect the audio element to have been paused
    expect(mockPause).toHaveBeenCalled();
  });

  test("should fall back to browser speechSynthesis when backend fails", async () => {
    // GIVEN the backend synthesis rejects with an error
    mockSynthesize.mockRejectedValue(new Error("Backend unavailable"));

    // WHEN the hook is rendered and speak is called
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Hello world");
    });

    // THEN expect window.speechSynthesis.speak to have been called as a fallback
    await waitFor(() => {
      expect(mockSpeak).toHaveBeenCalled();
    });

    // AND expect the status to be playing (via browser fallback)
    expect(result.current.status).toBe("playing");
  });

  test("should apply language fallback for ny-ZM", async () => {
    // GIVEN the current language is ny-ZM (which falls back to en-US)
    mockLanguage = "ny-ZM";
    mockSynthesize.mockResolvedValue("blob:mock-audio-url");

    // WHEN the hook is rendered and speak is called
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Moni");
    });

    // THEN expect synthesize to have been called with en-US (the fallback language)
    await waitFor(() => {
      expect(mockSynthesize).toHaveBeenCalledWith("Moni", "en-US");
    });
  });

  test("should strip markdown before sending to service", async () => {
    // GIVEN a message with markdown formatting
    const givenMarkdownText = "**bold** and *italic* and [link](http://example.com)";
    mockSynthesize.mockResolvedValue("blob:mock-audio-url");

    // WHEN the hook is rendered and speak is called with the markdown text
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak(givenMarkdownText);
    });

    // THEN expect synthesize to have been called with the cleaned text (markdown stripped)
    await waitFor(() => {
      expect(mockSynthesize).toHaveBeenCalledWith("bold and italic and link", "en-US");
    });
  });

  test("should transition back to idle when audio.onerror fires", async () => {
    // GIVEN the backend synthesis resolves with an audio URL
    mockSynthesize.mockResolvedValue("blob:mock-audio-url");

    // WHEN the hook is rendered and speak is called
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Hello world");
    });

    // AND the audio starts playing
    await waitFor(() => {
      expect(result.current.status).toBe("playing");
    });

    // AND an audio error occurs
    act(() => {
      if (mockAudioInstance.onerror) {
        mockAudioInstance.onerror();
      }
    });

    // THEN expect the status to transition back to idle
    await waitFor(() => {
      expect(result.current.status).toBe("idle");
    });
  });

  test("should return to idle and ignore synthesis result when stop is called during loading", async () => {
    // GIVEN a deferred promise for backend synthesis (does not resolve immediately)
    let resolveSynthesize!: (value: string) => void;
    const givenSynthesizePromise = new Promise<string>((resolve) => {
      resolveSynthesize = resolve;
    });
    mockSynthesize.mockReturnValue(givenSynthesizePromise);

    // WHEN the hook is rendered and speak is called
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak("Hello world");
    });

    // THEN expect the status to be loading
    expect(result.current.status).toBe("loading");

    // WHEN stop is called while still loading
    act(() => {
      result.current.stop();
    });

    // THEN expect the status to return to idle
    expect(result.current.status).toBe("idle");

    // WHEN the synthesis promise eventually resolves
    await act(async () => {
      resolveSynthesize("blob:mock-audio-url");
    });

    // THEN expect the status to remain idle (the aborted signal prevents playback)
    expect(result.current.status).toBe("idle");
    // AND expect no audio to have been created (the .then() was skipped)
    expect(mockPlay).not.toHaveBeenCalled();
  });

  test("should not speak empty text", () => {
    // GIVEN an empty text string
    const givenEmptyText = "";

    // WHEN the hook is rendered and speak is called with empty text
    const { result } = renderHook(() => useTextToSpeech());

    act(() => {
      result.current.speak(givenEmptyText);
    });

    // THEN expect synthesize to not have been called
    expect(mockSynthesize).not.toHaveBeenCalled();
    // AND expect the status to remain idle
    expect(result.current.status).toBe("idle");
  });
});
