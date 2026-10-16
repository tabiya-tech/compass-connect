// mute chatty console
import "src/_test_utilities/consoleMock";
import AuthenticationServiceFactory from "src/auth/services/Authentication.service.factory";
import { PersistentStorageService } from "src/app/PersistentStorageService/PersistentStorageService";
import { AuthenticationServices } from "src/auth/auth.types";
import FirebaseCustomTokenAuthenticationService from "src/auth/services/FirebaseAuthenticationService/customTokenAuth/FirebaseCustomTokenAuthenticationService";
import FirebaseEmailAuthenticationService from "src/auth/services/FirebaseAuthenticationService/emailAuth/FirebaseEmailAuthentication.service";
import FirebaseInvitationCodeAuthenticationService from "src/auth/services/FirebaseAuthenticationService/invitationCodeAuth/FirebaseInvitationCodeAuthenticationService";
import FirebaseSocialAuthenticationService from "src/auth/services/FirebaseAuthenticationService/socialAuth/FirebaseSocialAuthentication.service";

jest.mock("firebase/compat/app", () => {
  return {
    initializeApp: jest.fn(),
    auth: jest.fn().mockReturnValue({
      signOut: jest.fn(),
      onAuthStateChanged: jest.fn(),
    }),
  };
});

describe("AuthenticationServiceFactory.getCurrentAuthenticationService", () => {
  afterEach(() => {
    PersistentStorageService.clearLoginMethod();
  });

  test.each([
    [AuthenticationServices.FIREBASE_ANONYMOUS, FirebaseInvitationCodeAuthenticationService],
    [AuthenticationServices.FIREBASE_EMAIL, FirebaseEmailAuthenticationService],
    [AuthenticationServices.FIREBASE_SOCIAL, FirebaseSocialAuthenticationService],
    [AuthenticationServices.FIREBASE_CUSTOM_TOKEN, FirebaseCustomTokenAuthenticationService],
  ])("should return the service of the stored login method %s", (givenLoginMethod, expectedService) => {
    // GIVEN the login method is stored
    PersistentStorageService.setLoginMethod(givenLoginMethod);

    // WHEN the current authentication service is requested
    const actual = AuthenticationServiceFactory.getCurrentAuthenticationService();

    // THEN it is the service of that login method
    expect(actual).toBe(expectedService.getInstance());
  });

  test("should return null and clear an unknown login method", () => {
    // GIVEN an unknown login method is stored
    PersistentStorageService.setLoginMethod("FOO" as AuthenticationServices);

    // WHEN the current authentication service is requested
    const actual = AuthenticationServiceFactory.getCurrentAuthenticationService();

    // THEN there is none, and the stored method is cleared
    expect(actual).toBeNull();
    expect(PersistentStorageService.getLoginMethod()).toBeNull();
  });
});
