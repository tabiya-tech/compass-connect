import { getBackendUrl } from "src/envService";
import { StatusCodes } from "http-status-codes";
import { customFetch } from "src/utils/customFetch/customFetch";

export default class TextToSpeechService {
  private static instance: TextToSpeechService;
  readonly apiServerUrl: string;
  private cache: Map<string, string> = new Map(); // cacheKey -> objectURL
  private cacheKeys: string[] = []; // for LRU eviction order
  private static MAX_CACHE_SIZE = 20;

  private constructor() {
    this.apiServerUrl = getBackendUrl();
  }

  static getInstance(): TextToSpeechService {
    if (!TextToSpeechService.instance) {
      TextToSpeechService.instance = new TextToSpeechService();
    }
    return TextToSpeechService.instance;
  }

  private getCacheKey(text: string, language: string): string {
    return `${language}::${text}`;
  }

  async synthesize(text: string, language: string): Promise<string> {
    const cacheKey = this.getCacheKey(text, language);
    const cached = this.cache.get(cacheKey);
    if (cached) return cached;

    const url = `${this.apiServerUrl}/text-to-speech/synthesize`;
    const response = await customFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language }),
      expectedStatusCode: StatusCodes.OK,
      serviceName: "TextToSpeechService",
      serviceFunction: "synthesize",
      failureMessage: "Failed to synthesize speech",
      expectedContentType: "audio/mpeg",
      compressRequestBody: false,
    });

    const audioBlob = await response.blob();
    const objectUrl = URL.createObjectURL(audioBlob);

    // LRU cache management
    if (this.cacheKeys.length >= TextToSpeechService.MAX_CACHE_SIZE) {
      const evictKey = this.cacheKeys.shift()!;
      const evictUrl = this.cache.get(evictKey);
      if (evictUrl) URL.revokeObjectURL(evictUrl);
      this.cache.delete(evictKey);
    }
    this.cache.set(cacheKey, objectUrl);
    this.cacheKeys.push(cacheKey);

    return objectUrl;
  }
}
