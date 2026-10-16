import { StatusCodes } from "http-status-codes";
import { getBackendUrl } from "src/envService";
import { customFetch } from "src/utils/customFetch/customFetch";
import { HandoffExchangeResponse } from "src/handoff/handoff.types";

export default class HandoffService {
  private static instance: HandoffService;

  readonly exchangeEndpointUrl: string;

  constructor() {
    this.exchangeEndpointUrl = `${getBackendUrl()}/handoff/exchange`;
  }

  /**
   * Get the singleton instance of the HandoffService.
   * @returns {HandoffService} The singleton instance of the HandoffService.
   */
  static getInstance(): HandoffService {
    if (!HandoffService.instance) {
      HandoffService.instance = new HandoffService();
    }
    return HandoffService.instance;
  }

  /**
   * Exchanges the token of a hand-off link for a Firebase custom token.
   * The token is a credential: it is sent in the body and never put in a log or an error message.
   * @param {string} token - The token from the hand-off link.
   * @returns {Promise<HandoffExchangeResponse>} The custom token and where the user lands.
   * @throws {RestAPIError} 401 if the link is unknown, expired or replaced by a newer one.
   */
  async exchange(token: string): Promise<HandoffExchangeResponse> {
    const response = await customFetch(this.exchangeEndpointUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      expectedStatusCode: StatusCodes.OK,
      serviceName: "HandoffService",
      serviceFunction: "exchange",
      failureMessage: "Failed to exchange the hand-off link",
      authRequired: false,
      retryOnFailedToFetch: true,
    });

    return JSON.parse(await response.text());
  }
}
