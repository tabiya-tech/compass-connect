import "src/_test_utilities/consoleMock";

import { StatusCodes } from "http-status-codes";
import HandoffService from "src/handoff/handoff.service";
import { HandoffAction, HandoffExchangeResponse } from "src/handoff/handoff.types";
import { setupAPIServiceSpy } from "src/_test_utilities/fetchSpy";

describe("HandoffService", () => {
  // GIVEN a backend URL is returned by the envService
  const givenApiServerUrl = "/path/to/api";
  beforeEach(() => {
    jest.spyOn(require("src/envService"), "getBackendUrl").mockReturnValue(givenApiServerUrl);
  });
  afterEach(() => {
    jest.resetAllMocks();
  });

  test("should construct the service with the exchange endpoint", () => {
    expect(new HandoffService().exchangeEndpointUrl).toEqual(`${givenApiServerUrl}/handoff/exchange`);
  });

  test("should return the same instance", () => {
    expect(HandoffService.getInstance()).toBe(HandoffService.getInstance());
  });

  describe("exchange", () => {
    test("should POST the link token without authentication and return the custom token", async () => {
      // GIVEN the exchange endpoint responds with a custom token
      const givenResponse: HandoffExchangeResponse = {
        custom_token: "custom-token",
        action: HandoffAction.BUILD_PROFILE,
      };
      const fetchSpy = setupAPIServiceSpy(StatusCodes.OK, givenResponse, "application/json;charset=UTF-8");

      // WHEN the link token is exchanged
      const givenToken = "link-token";
      const actual = await new HandoffService().exchange(givenToken);

      // THEN the token is sent in the body of an unauthenticated POST
      expect(fetchSpy).toHaveBeenCalledWith(`${givenApiServerUrl}/handoff/exchange`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: givenToken }),
        expectedStatusCode: StatusCodes.OK,
        serviceName: "HandoffService",
        serviceFunction: "exchange",
        failureMessage: "Failed to exchange the hand-off link",
        authRequired: false,
        retryOnFailedToFetch: true,
      });
      // AND the token is not in the failure message (it would end up in logs)
      expect(fetchSpy.mock.calls[0][1].failureMessage).not.toContain(givenToken);
      // AND the response is returned
      expect(actual).toEqual(givenResponse);
    });

    test("should throw when the request fails", async () => {
      // GIVEN the request fails
      const givenError = new Error("unauthorized");
      jest.spyOn(require("src/utils/customFetch/customFetch"), "customFetch").mockRejectedValueOnce(givenError);

      // WHEN the link token is exchanged
      // THEN the error is thrown
      await expect(new HandoffService().exchange("link-token")).rejects.toThrow(givenError);
    });
  });
});
