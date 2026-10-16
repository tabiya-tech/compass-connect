// mute chatty console
import "src/_test_utilities/consoleMock";
import FirebaseCustomTokenAuthenticationService from "src/auth/services/FirebaseAuthenticationService/customTokenAuth/FirebaseCustomTokenAuthenticationService";
import firebase from "firebase/compat/app";
import UserPreferencesService from "src/userPreferences/UserPreferencesService/userPreferences.service";
import { UserPreference } from "src/userPreferences/UserPreferencesService/userPreferences.types";
import { resetAllMethodMocks } from "src/_test_utilities/resetAllMethodMocks";
import AuthenticationStateService from "src/auth/services/AuthenticationState.service";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import { PersistentStorageService } from "src/app/PersistentStorageService/PersistentStorageService";
import StdFirebaseAuthenticationService, {
  FirebaseToken,
  FirebaseTokenProvider,
  FirebaseTokenValidationFailureCause,
} from "src/auth/services/FirebaseAuthenticationService/StdFirebaseAuthenticationService";
import AuthenticationService from "src/auth/services/Authentication.service";
import { AuthenticationServices } from "src/auth/auth.types";

jest.mock("jwt-decode");

jest.mock("firebase/compat/app", () => {
  return {
    initializeApp: jest.fn(),
    auth: jest.fn().mockReturnValue({
      signInWithCustomToken: jest.fn(),
      signInAnonymously: jest.fn(),
      signOut: jest.fn(),
      onAuthStateChanged: jest.fn(),
    }),
  };
});

describe("FirebaseCustomTokenAuthenticationService", () => {
  const authService = FirebaseCustomTokenAuthenticationService.getInstance();

  beforeEach(() => {
    jest.clearAllMocks();
    AuthenticationStateService.getInstance().setUser(null);
    UserPreferencesStateService.getInstance().clearUserPreferences();
    resetAllMethodMocks(UserPreferencesService.getInstance());
  });

  test("should construct a singleton", () => {
    // WHEN the singleton is constructed twice
    const instance = FirebaseCustomTokenAuthenticationService.getInstance();
    const newInstance = FirebaseCustomTokenAuthenticationService.getInstance();

    // THEN it is the same instance
    expect(instance).toBeDefined();
    expect(newInstance).toBe(instance);
  });

  describe("login", () => {
    const givenUser = { id: "user-1", name: "foo@bar.baz", email: "foo@bar.baz" };

    test("should sign in with the custom token and load the existing preferences", async () => {
      // GIVEN firebase signs in with the custom token
      const givenCustomToken = "custom-token";
      const givenIdToken = "id-token";
      jest.spyOn(firebase.auth(), "signInWithCustomToken").mockResolvedValue({
        user: { getIdToken: jest.fn().mockResolvedValue(givenIdToken) },
      } as unknown as firebase.auth.UserCredential);
      // AND the ID token is decoded into a user
      jest.spyOn(authService, "getUser").mockReturnValue(givenUser);
      // AND the user already has preferences (the backend created them)
      const givenPreferences = { user_id: givenUser.id, sessions: [1] } as unknown as UserPreference;
      jest.spyOn(UserPreferencesService.getInstance(), "getUserPreferences").mockResolvedValueOnce(givenPreferences);
      const createSpy = jest.spyOn(UserPreferencesService.getInstance(), "createUserPreferences");
      // AND the login method is stored
      const setLoginMethodSpy = jest.spyOn(PersistentStorageService, "setLoginMethod");

      // WHEN logging in with the custom token
      const actualToken = await authService.login(givenCustomToken);

      // THEN firebase signed in with it, and the ID token is returned
      expect(firebase.auth().signInWithCustomToken).toHaveBeenCalledWith(givenCustomToken);
      expect(actualToken).toEqual(givenIdToken);
      // AND the login method is remembered, so the session survives a reload
      expect(setLoginMethodSpy).toHaveBeenCalledWith(AuthenticationServices.FIREBASE_CUSTOM_TOKEN);
      // AND the user and the existing preferences are in the state, nothing was registered
      expect(AuthenticationStateService.getInstance().getUser()).toEqual(givenUser);
      expect(UserPreferencesStateService.getInstance().getUserPreferences()).toEqual(givenPreferences);
      expect(createSpy).not.toHaveBeenCalled();
      // AND no errors or warnings were logged
      expect(console.error).not.toHaveBeenCalled();
      expect(console.warn).not.toHaveBeenCalled();
    });

    test("should throw when firebase refuses the custom token", async () => {
      // GIVEN firebase refuses the custom token
      jest.spyOn(firebase.auth(), "signInWithCustomToken").mockRejectedValue({
        code: "auth/invalid-custom-token",
        message: "invalid custom token",
      });

      // WHEN logging in
      // THEN it fails
      await expect(authService.login("custom-token")).rejects.toThrow();
      // AND nobody is logged in
      expect(AuthenticationStateService.getInstance().getUser()).toBeNull();
    });

    test("should throw when firebase returns no user", async () => {
      // GIVEN firebase signs in without a user
      jest.spyOn(firebase.auth(), "signInWithCustomToken").mockResolvedValue({
        user: null,
      } as unknown as firebase.auth.UserCredential);

      // WHEN logging in
      // THEN it fails
      await expect(authService.login("custom-token")).rejects.toThrow("User not found");
    });
  });

  describe("isTokenValid", () => {
    const givenDecodedToken = { user_id: "user-1" } as unknown as FirebaseToken;

    test.each([
      [true, undefined],
      [false, FirebaseTokenValidationFailureCause.INVALID_FIREBASE_SIGN_IN_PROVIDER],
    ])(
      "should expect a token from a custom token sign-in (valid=%s)",
      (givenFirebaseTokenValid: boolean, givenFailureCause?: FirebaseTokenValidationFailureCause) => {
        // GIVEN the token is a well-formed, unexpired token
        const baseCheckSpy = jest
          .spyOn(AuthenticationService.prototype, "isTokenValid")
          .mockReturnValue({ isValid: true, decodedToken: givenDecodedToken });
        // AND the firebase check gives the given result
        const firebaseCheckSpy = jest
          .spyOn(StdFirebaseAuthenticationService.getInstance(), "isFirebaseTokenValid")
          .mockReturnValue({ isValid: givenFirebaseTokenValid, failureCause: givenFailureCause });

        // WHEN the token is checked
        const actual = authService.isTokenValid("token");

        // THEN the firebase check expects the custom sign-in provider
        expect(firebaseCheckSpy).toHaveBeenCalledWith(givenDecodedToken, FirebaseTokenProvider.CUSTOM);
        // AND its result is returned
        expect(actual.isValid).toBe(givenFirebaseTokenValid);

        baseCheckSpy.mockRestore();
        firebaseCheckSpy.mockRestore();
      }
    );
  });

  describe("logout", () => {
    test("should log out of firebase and clear the user", async () => {
      // GIVEN a logged in user
      AuthenticationStateService.getInstance().setUser({ id: "user-1", name: "foo", email: "foo@bar.baz" });
      const stdLogoutSpy = jest.spyOn(StdFirebaseAuthenticationService.getInstance(), "logout").mockResolvedValue();

      // WHEN logging out
      await authService.logout();

      // THEN firebase was logged out and the user cleared
      expect(stdLogoutSpy).toHaveBeenCalled();
      expect(AuthenticationStateService.getInstance().getUser()).toBeNull();
    });
  });

  describe("isProviderSessionValid", () => {
    it.each([true, false])("should return '%s' like the firebase session check", async (expected) => {
      // GIVEN the firebase session check gives the expected result
      jest.spyOn(StdFirebaseAuthenticationService.getInstance(), "isAuthSessionValid").mockResolvedValue(expected);

      // WHEN the provider session is checked
      // THEN it returns the same result
      expect(await authService.isProviderSessionValid()).toBe(expected);
    });
  });
});
