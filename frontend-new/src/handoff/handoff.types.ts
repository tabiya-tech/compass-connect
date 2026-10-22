/**
 * Where the user lands after the hand-off link logged them in.
 */
export enum HandoffAction {
  /** The Compass home page. */
  CREATE = "create",
  /** The conversation that builds the skills report. */
  BUILD_PROFILE = "build_profile",
}

export interface HandoffExchangeResponse {
  custom_token: string;
  action: HandoffAction;
}
