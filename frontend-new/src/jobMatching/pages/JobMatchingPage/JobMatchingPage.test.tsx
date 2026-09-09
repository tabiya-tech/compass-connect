// standard mocks
import "src/_test_utilities/sentryMock";
import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import { render, screen, fireEvent, waitFor } from "src/_test_utilities/test-utils";
import AuthenticationStateService from "src/auth/services/AuthenticationState.service";
import JobMatchingPage from "src/jobMatching/pages/JobMatchingPage/JobMatchingPage";
import { useJobs } from "src/jobMatching/hooks/useJobs";
import JobService from "src/jobMatching/services/JobService";
import type { JobRow } from "src/jobMatching/types";
import MetricsService from "src/metrics/metricsService";
import { EventType } from "src/metrics/types";

jest.mock("src/metrics/metricsService", () => ({
  __esModule: true,
  default: { getInstance: jest.fn().mockReturnValue({ sendMetricsEvent: jest.fn() }) },
}));

jest.mock("src/auth/services/AuthenticationState.service", () => ({
  __esModule: true,
  default: { getInstance: jest.fn().mockReturnValue({ getUser: jest.fn() }) },
}));

jest.mock("src/jobMatching/hooks/useJobs", () => {
  const actual = jest.requireActual("src/jobMatching/hooks/useJobs");
  return { ...actual, __esModule: true, useJobs: jest.fn() };
});

jest.mock("src/jobMatching/services/JobService", () => ({
  __esModule: true,
  default: { getInstance: jest.fn().mockReturnValue({ listJobs: jest.fn(), getMatchedJobs: jest.fn() }) },
}));

jest.mock("src/home/components/Footer/Footer", () => ({
  __esModule: true,
  default: () => <span data-testid="footer-mock" />,
}));

const GIVEN_USER_ID = "user-abc";

const givenJobRow = (overrides: Partial<JobRow> = {}): JobRow => ({
  id: "1",
  jobUuid: "job-uuid-1",
  jobTitle: "Software Engineer",
  company: "Acme Corp",
  category: "Technology",
  employmentType: "full time",
  location: "Lusaka",
  posted: "2026-01-01",
  ...overrides,
});

const setupJobs = (rows: JobRow[]) => {
  (useJobs as jest.Mock).mockReturnValue({
    jobs: rows,
    loading: false,
    error: null,
    pageIndex: 1,
    totalItems: rows.length,
    hasPrev: false,
    hasNext: false,
    goNext: jest.fn(),
    goPrev: jest.fn(),
    reload: jest.fn(),
  });
};

const sendMetricsEvent = () => MetricsService.getInstance().sendMetricsEvent as jest.Mock;

describe("JobMatchingPage job-viewed metrics", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [],
      meta: { limit: 20, next_cursor: null, has_more: false, total: 0 },
    });
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue({ id: GIVEN_USER_ID });
  });

  test("should send a job viewed event when a listing is opened", async () => {
    // GIVEN the browse tab lists one job with a uuid
    const givenJob = givenJobRow();
    setupJobs([givenJob]);
    render(<JobMatchingPage />);

    // WHEN the user clicks the row to open the listing
    fireEvent.click(await screen.findByText("Software Engineer"));

    // THEN a JOB_VIEWED event is sent for that listing's uuid and the signed-in user
    await waitFor(() => expect(sendMetricsEvent()).toHaveBeenCalledTimes(1));
    const actualEvent = sendMetricsEvent().mock.calls[0][0];
    expect(actualEvent).toEqual(
      expect.objectContaining({
        event_type: EventType.JOB_VIEWED,
        user_id: GIVEN_USER_ID,
        job_id: "job-uuid-1",
      })
    );
    // AND the timestamp is an ISO string the backend can parse
    expect(new Date(actualEvent.timestamp).toISOString()).toBe(actualEvent.timestamp);
  });

  test("should not send a job viewed event for a listing with no uuid", async () => {
    // GIVEN the browse tab lists a job the API returned without a uuid
    setupJobs([givenJobRow({ jobUuid: undefined })]);
    render(<JobMatchingPage />);

    // WHEN the user clicks the row to open the listing
    fireEvent.click(await screen.findByText("Software Engineer"));

    // THEN no event is sent — the row key would not aggregate into anything meaningful
    expect(sendMetricsEvent()).not.toHaveBeenCalled();
  });

  test("should not send a job viewed event when no user is signed in", async () => {
    // GIVEN there is no authenticated user
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue(null);
    setupJobs([givenJobRow()]);
    render(<JobMatchingPage />);

    // WHEN the user clicks the row to open the listing
    fireEvent.click(await screen.findByText("Software Engineer"));

    // THEN no event is sent, since the event is attributed per user
    expect(sendMetricsEvent()).not.toHaveBeenCalled();
  });
});
