import { firebaseAuth } from "src/auth/firebaseConfig";
import { castToFirebaseError, getFirebaseErrorFactory } from "src/error/FirebaseError/firebaseError";
import { FirebaseErrorCodes } from "src/error/FirebaseError/firebaseError.constants";
import StdFirebaseAuthenticationService, {
  FirebaseToken,
  FirebaseTokenProvider,
} from "src/auth/services/FirebaseAuthenticationService/StdFirebaseAuthenticationService";
import { PersistentStorageService } from "src/app/PersistentStorageService/PersistentStorageService";
import { AuthenticationServices, TabiyaUser } from "src/auth/auth.types";
import AuthenticationService from "src/auth/services/Authentication.service";
import { pushToDataLayer } from "src/gtmInit";
import { formatTokenForLogging } from "src/auth/utils/formatTokenForLogging";
import { TokenError } from "src/error/commonErrors";

/**
 * Login for users sent by another platform through a hand-off link.
 * The backend creates the user and their preferences and mints a Firebase custom token for them,
 * so unlike the other login methods nothing is registered here.
 */
class FirebaseCustomTokenAuthenticationService extends AuthenticationService {
  private static instance: FirebaseCustomTokenAuthenticationService;
  private readonly stdFirebaseAuthServiceInstance: StdFirebaseAuthenticationService;

  private constructor() {
    super();
    this.stdFirebaseAuthServiceInstance = StdFirebaseAuthenticationService.getInstance();
  }

  /**
   * Get the singleton instance of the FirebaseCustomTokenAuthenticationService.
   * @returns {FirebaseCustomTokenAuthenticationService} The singleton instance.
   */
  static getInstance(): FirebaseCustomTokenAuthenticationService {
    if (!this.instance) {
      this.instance = new this();
    }
    return this.instance;
  }

  /**
   * handle login with a custom token minted by the backend
   * @param {string} customToken - The Firebase custom token
   * @returns {Promise<string>} The firebase token
   * @throws {FirebaseError} If the firebase authentication fails
   */
  async login(customToken: string): Promise<string> {
    const firebaseErrorFactory = getFirebaseErrorFactory("CustomTokenAuthService", "handleCustomTokenLogin");
    let userCredential;
    try {
      userCredential = await firebaseAuth.signInWithCustomToken(customToken);
    } catch (error) {
      throw castToFirebaseError(error, firebaseErrorFactory);
    }

    if (!userCredential.user) {
      throw firebaseErrorFactory(FirebaseErrorCodes.USER_NOT_FOUND, "User not found", {});
    }
    const token = await userCredential.user.getIdToken();
    // set the login method for future reference (e.g. reload, logout)
    PersistentStorageService.setLoginMethod(AuthenticationServices.FIREBASE_CUSTOM_TOKEN);

    // the preferences already exist, onSuccessfulLogin loads them
    await super.onSuccessfulLogin(token);

    pushToDataLayer("user_login", { method: "handoff" });

    return token;
  }

  /**
   * Cleanup resources used by the authentication service
   * @throws {Error} If cleanup fails
   */
  async cleanup(): Promise<void> {
    this.stdFirebaseAuthServiceInstance.cleanup();
  }

  /**
   * Logout the current user
   */
  async logout(): Promise<void> {
    await this.stdFirebaseAuthServiceInstance.logout();
    await super.onSuccessfulLogout();
  }

  /**
   * Refresh the current authentication token
   * @throws {Error} If token refresh fails, will attempt to logout
   */
  async refreshToken(): Promise<void> {
    try {
      const newToken = await this.stdFirebaseAuthServiceInstance.refreshToken();
      // call the parent class method once the token is successfully refreshed
      await super.onSuccessfulRefresh(newToken);
    } catch (error) {
      console.error(new TokenError("error refreshing token", error));
      // if token refresh fails, log the error and do nothing
    }
  }

  /**
   * Get user information from token
   * @param {string} token - The authentication token
   * @returns {TabiyaUser | null} The user information or null if token is invalid
   */
  getUser(token: string): TabiyaUser | null {
    const { isValid, decodedToken, failureCause } = this.isTokenValid(token);

    if (!isValid) {
      console.warn(new TokenError(`invalid token: ${formatTokenForLogging(token)}`, failureCause));
      return null;
    }
    return this.stdFirebaseAuthServiceInstance.getUserFromDecodedToken(decodedToken!);
  }

  /**
   * Check if the token is a valid firebase token obtained with a custom token
   * @param {string} token - The authentication token
   * @returns {boolean} True if the token is valid, false otherwise
   */
  public isTokenValid(token: string): { isValid: boolean; decodedToken: FirebaseToken | null; failureCause?: string } {
    const {
      isValid: isValidToken,
      decodedToken,
      failureCause: tokenValidationFailureCause,
    } = super.isTokenValid(token);

    if (!isValidToken) {
      console.debug(`token is invalid: ${tokenValidationFailureCause} - ${formatTokenForLogging(token)}`);
      return { isValid: false, decodedToken: null, failureCause: tokenValidationFailureCause! };
    }

    const { isValid: isValidFirebaseToken, failureCause: firebaseTokenValidationFailureCause } =
      this.stdFirebaseAuthServiceInstance.isFirebaseTokenValid(
        decodedToken as FirebaseToken,
        FirebaseTokenProvider.CUSTOM
      );
    if (!isValidFirebaseToken) {
      console.debug(
        `token is not a valid firebase token: ${firebaseTokenValidationFailureCause} - ${formatTokenForLogging(token)}`
      );
      return { isValid: false, decodedToken: null, failureCause: firebaseTokenValidationFailureCause! };
    }

    return { isValid: true, decodedToken: decodedToken as FirebaseToken };
  }

  /**
   * Checks if a firebase active session/user exists in the local storage. (i.e.: IndexDB)
   *
   * @returns {boolean} True if an active session exists, false otherwise.
   */
  async isProviderSessionValid(): Promise<boolean> {
    return await this.stdFirebaseAuthServiceInstance.isAuthSessionValid();
  }
}

export default FirebaseCustomTokenAuthenticationService;
