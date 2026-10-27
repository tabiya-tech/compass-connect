// mute chatty console
import "src/_test_utilities/consoleMock";

import React from "react";
import { render, screen, waitFor } from "src/_test_utilities/test-utils";
import { act } from "@testing-library/react";
import { useNavigate } from "react-router-dom";
import Handoff, { DATA_TEST_ID } from "src/handoff/Handoff";
import { routerPaths } from "src/app/routerPaths";
import HandoffService from "src/handoff/handoff.service";
import { HandoffAction } from "src/handoff/handoff.types";
import FirebaseCustomTokenAuthenticationService from "src/auth/services/FirebaseAuthenticationService/customTokenAuth/FirebaseCustomTokenAuthenticationService";
import AuthenticationStateService from "src/auth/services/AuthenticationState.service";
import AuthenticationServiceFactory from "src/auth/services/Authentication.service.factory";
import AuthenticationService from "src/auth/services/Authentication.service";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import { UserPreference } from "src/userPreferences/UserPreferencesService/userPreferences.types";
import * as envService from "src/envService";

// Mock the router so we can spy on navigation and inject the location.
jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    __esModule: true,
    useNavigate: jest.fn().mockReturnValue(jest.fn()),
    useLocation: jest.fn(),
  };
});

const { useLocation } = jest.requireMock("react-router-dom") as { useLocation: jest.Mock };

const setSearch = (search: string) => {
  useLocation.mockReturnValue({ pathname: routerPaths.HANDOFF, search, hash: "", state: null, key: "" });
};

const givenCustomToken = "custom-token-of-user-1";

const preferences = (acceptedTc: Date | undefined): UserPreference =>
  ({ user_id: "user-1", sessions: [1], accepted_tc: acceptedTc }) as unknown as UserPreference;

describe("Handoff", () => {
  let exchangeSpy: jest.SpyInstance;
  let loginSpy: jest.SpyInstance;

  // the user's preferences after the login
  const givenLoginSetsPreferences = (acceptedTc: Date | undefined) => {
    loginSpy.mockImplementation(async () => {
      UserPreferencesStateService.getInstance().setUserPreferences(preferences(acceptedTc));
      return "id-token";
    });
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (console.error as jest.Mock).mockClear();
    (console.warn as jest.Mock).mockClear();
    AuthenticationStateService.getInstance().setUser(null);
    UserPreferencesStateService.getInstance().clearUserPreferences();
    exchangeSpy = jest.spyOn(HandoffService.getInstance(), "exchange");
    loginSpy = jest.spyOn(FirebaseCustomTokenAuthenticationService.getInstance(), "login");
  });

  afterEach(() => {
    exchangeSpy.mockRestore();
    loginSpy.mockRestore();
  });

  test("should remove the token from the URL right away", async () => {
    // GIVEN a link with a token
    setSearch("?token=link-token");
    exchangeSpy.mockReturnValue(new Promise(() => {})); // still exchanging

    // WHEN the page is opened
    render(<Handoff />);

    // THEN the token is removed from the URL, replacing the history entry
    expect(useNavigate()).toHaveBeenCalledWith({ pathname: routerPaths.HANDOFF, search: "" }, { replace: true });
    // AND the user sees that they are being signed in
    expect(screen.getByTestId(DATA_TEST_ID.LOADING_SPINNER)).toBeInTheDocument();
  });

  test("should log a new user in and show the consent first, then the conversation", async () => {
    // GIVEN a link to the conversation, for a user who is not logged in
    setSearch("?token=link-token");
    exchangeSpy.mockResolvedValue({
      custom_token: givenCustomToken,
      action: HandoffAction.BUILD_PROFILE,
    });
    // AND the user has not given the consent yet
    givenLoginSetsPreferences(undefined);

    // WHEN the page is opened
    render(<Handoff />);

    // THEN the link token is exchanged and the user logged in with the custom token
    await waitFor(() => expect(loginSpy).toHaveBeenCalledWith(givenCustomToken));
    expect(exchangeSpy).toHaveBeenCalledWith("link-token");
    // AND they go to the consent page, which then sends them to the conversation
    await waitFor(() =>
      expect(useNavigate()).toHaveBeenCalledWith(routerPaths.CONSENT, {
        replace: true,
        state: { afterConsent: routerPaths.SKILLS_INTERESTS },
      })
    );
    expect(console.error).not.toHaveBeenCalled();
  });

  test.each([
    [HandoffAction.BUILD_PROFILE, routerPaths.SKILLS_INTERESTS],
    [HandoffAction.CREATE, routerPaths.ROOT],
  ])("should land a user who gave the consent where the %s link says", async (givenAction, expectedPath) => {
    // GIVEN a link, for a user who already gave the consent
    setSearch("?token=link-token");
    exchangeSpy.mockResolvedValue({ custom_token: givenCustomToken, action: givenAction });
    givenLoginSetsPreferences(new Date());

    // WHEN the page is opened
    render(<Handoff />);

    // THEN they land on the page of the action
    await waitFor(() => expect(useNavigate()).toHaveBeenCalledWith(expectedPath, { replace: true }));
  });

  test("should land the user on home when the module of the action is disabled", async () => {
    // GIVEN the deployment disables the module the conversation link lands in
    const getDisabledModulesSpy = jest.spyOn(envService, "getDisabledModules").mockReturnValue(["skills_discovery"]);
    // AND a link to the conversation, for a user who already gave the consent
    setSearch("?token=link-token");
    exchangeSpy.mockResolvedValue({ custom_token: givenCustomToken, action: HandoffAction.BUILD_PROFILE });
    givenLoginSetsPreferences(new Date());

    // WHEN the page is opened
    render(<Handoff />);

    // THEN they land on home instead
    await waitFor(() => expect(useNavigate()).toHaveBeenCalledWith(routerPaths.ROOT, { replace: true }));
    // AND the misconfiguration is logged
    expect(console.warn).toHaveBeenCalled();
    getDisabledModulesSpy.mockRestore();
  });

  test.each([
    ["someone else", "someone-else"],
    ["the same user", "user-1"],
  ])("should log out %s before logging the user in", async (_description, givenLoggedInUserId) => {
    // GIVEN a user is logged in on this device
    AuthenticationStateService.getInstance().setUser({ id: givenLoggedInUserId, name: "bar", email: "bar@baz.foo" });
    const givenCurrentService = { logout: jest.fn().mockResolvedValue(undefined) } as unknown as AuthenticationService;
    const factorySpy = jest
      .spyOn(AuthenticationServiceFactory, "getCurrentAuthenticationService")
      .mockReturnValue(givenCurrentService);
    setSearch("?token=link-token");
    exchangeSpy.mockResolvedValue({ custom_token: givenCustomToken, action: HandoffAction.CREATE });
    givenLoginSetsPreferences(new Date());

    // WHEN the page is opened
    render(<Handoff />);

    // THEN that user is logged out, then the user of the link is logged in
    await waitFor(() => expect(loginSpy).toHaveBeenCalledWith(givenCustomToken));
    expect(givenCurrentService.logout).toHaveBeenCalled();
    expect((givenCurrentService.logout as jest.Mock).mock.invocationCallOrder[0]).toBeLessThan(
      loginSpy.mock.invocationCallOrder[0]
    );
    factorySpy.mockRestore();
  });

  test("should show an error when the link has no token", async () => {
    // GIVEN a link without a token
    setSearch("");

    // WHEN the page is opened
    render(<Handoff />);

    // THEN the user sees that the link cannot be used
    expect(await screen.findByTestId(DATA_TEST_ID.ERROR_TITLE)).toBeInTheDocument();
    expect(exchangeSpy).not.toHaveBeenCalled();
  });

  test("should show an error when the link is not valid, with a way to sign in", async () => {
    // GIVEN the backend refuses the link (expired, replaced or unknown)
    setSearch("?token=link-token");
    exchangeSpy.mockRejectedValue(new Error("401"));

    // WHEN the page is opened
    render(<Handoff />);

    // THEN the user sees that the link cannot be used
    expect(await screen.findByTestId(DATA_TEST_ID.ERROR_MESSAGE)).toBeInTheDocument();
    expect(loginSpy).not.toHaveBeenCalled();
    // AND the error is logged
    expect(console.error).toHaveBeenCalled();

    // AND WHEN they click the button
    act(() => {
      screen.getByTestId(DATA_TEST_ID.BACK_TO_LOGIN_BUTTON).click();
    });

    // THEN they go to the login page
    expect(useNavigate()).toHaveBeenCalledWith(routerPaths.LOGIN, { replace: true });
  });
});
