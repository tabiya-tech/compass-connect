/**
 * Where the user lands after the hand-off link logged them in.
 */
export enum HandoffAction {
  /** The Compass home page. */
  CREATE = "create",
  /** The conversation that builds the skills report. */
  SKILL_REPORT = "skill_report",
}

export interface HandoffExchangeResponse {
  custom_token: string;
  action: HandoffAction;
}
