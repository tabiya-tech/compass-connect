// standard mocks
import "src/_test_utilities/sentryMock";
import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import { render, screen, fireEvent, waitFor } from "src/_test_utilities/test-utils";
import AuthenticationStateService from "src/auth/services/AuthenticationState.service";
import JobMatchingPage from "src/jobMatching/pages/JobMatchingPage/JobMatchingPage";
import { useJobs } from "src/jobMatching/hooks/useJobs";
import { useMatchedJobs } from "src/jobMatching/hooks/useMatchedJobs";
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

jest.mock("src/jobMatching/hooks/useMatchedJobs", () => {
  const actual = jest.requireActual("src/jobMatching/hooks/useMatchedJobs");
  return { ...actual, __esModule: true, useMatchedJobs: jest.fn() };
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
  city: "Lusaka",
  province: "Lusaka",
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

const setupMatchedJobs = (rows: JobRow[]) => {
  (useMatchedJobs as jest.Mock).mockReturnValue({
    jobs: rows,
    loading: false,
    error: null,
    reload: jest.fn(),
    skillsSource: "s&i",
  });
};

const sendMetricsEvent = () => MetricsService.getInstance().sendMetricsEvent as jest.Mock;

/** Opens a column's filter popover and clicks the option with the given label. */
const selectFilterOption = async (columnKey: string, optionLabel: string) => {
  fireEvent.click(await screen.findByLabelText(`filter ${columnKey}`));
  const option = await screen.findByRole("menuitem", { name: optionLabel });
  fireEvent.click(option);
};

/** Opens the (multi-select) location filter popover and checks the checkbox for the given label. */
const checkLocationOption = async (optionLabel: string) => {
  if (screen.queryByRole("menuitemcheckbox", { name: "All" }) === null) {
    fireEvent.click(await screen.findByLabelText("filter location"));
  }
  const option = await screen.findByRole("menuitemcheckbox", { name: optionLabel });
  fireEvent.click(option);
};

describe("JobMatchingPage job-viewed metrics", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [],
      meta: { limit: 20, next_cursor: null, has_more: false, total: 0 },
    });
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue({ id: GIVEN_USER_ID });
    setupMatchedJobs([]);
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

describe("JobMatchingPage Browse Jobs location filter", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue({ id: GIVEN_USER_ID });
    setupMatchedJobs([]);
  });

  test("should offer the standalone city/province values as filter options, not the combined location string", async () => {
    // GIVEN the sampled jobs have separate city/province fields alongside a combined "City Province"
    // display string (e.g. "Lusaka Lusaka" — the matching service's location filter matches the
    // standalone city/province, not arbitrary substrings of the combined display value)
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [
        { uuid: "1", location: "Lusaka Lusaka", city: "Lusaka", province: "Lusaka" },
        { uuid: "2", location: "Mpika Muchinga", city: "Mpika", province: "Muchinga" },
      ],
      meta: { limit: 100, next_cursor: null, has_more: false, total: 2 },
    });
    setupJobs([givenJobRow({ location: "Lusaka Lusaka" })]);
    render(<JobMatchingPage />);

    // WHEN the user opens the location filter
    fireEvent.click(await screen.findByLabelText("filter location"));

    // THEN the combined "City Province" string never appears as a single option...
    expect(screen.queryByRole("menuitemcheckbox", { name: "Lusaka Lusaka" })).not.toBeInTheDocument();
    // ...only the standalone city/province values do, deduplicated across jobs
    expect(screen.getByRole("menuitemcheckbox", { name: "Lusaka" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: "Mpika" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemcheckbox", { name: "Muchinga" })).toBeInTheDocument();
    // AND an "All" checkbox is offered, checked by default (no filter applied)
    expect(screen.getByRole("menuitemcheckbox", { name: "All" })).toHaveAttribute("aria-checked", "true");
  });

  test("should query the backend with every selected location, letting the user pick more than one", async () => {
    // GIVEN two sampled jobs in different cities
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [
        { uuid: "1", location: "Chingola Copperbelt", city: "Chingola", province: "Copperbelt" },
        { uuid: "2", location: "Lusaka Lusaka", city: "Lusaka", province: "Lusaka" },
      ],
      meta: { limit: 100, next_cursor: null, has_more: false, total: 2 },
    });
    setupJobs([givenJobRow({ location: "Chingola Copperbelt" })]);
    render(<JobMatchingPage />);

    // WHEN the user checks both "Copperbelt" and "Lusaka"
    await checkLocationOption("Copperbelt");
    await checkLocationOption("Lusaka");

    // THEN useJobs (and in turn the backend query) receives both selected values, not the
    // combined "Chingola Copperbelt" string
    await waitFor(() => {
      const lastCallArgs = (useJobs as jest.Mock).mock.calls.at(-1)?.[0];
      expect(lastCallArgs?.location).toEqual(["Copperbelt", "Lusaka"]);
    });

    // AND the "All" checkbox is no longer checked, since specific locations are selected
    expect(screen.getByRole("menuitemcheckbox", { name: "All" })).toHaveAttribute("aria-checked", "false");
  });

  test("checking 'All' clears every specific location selection", async () => {
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [{ uuid: "1", location: "Chingola Copperbelt", city: "Chingola", province: "Copperbelt" }],
      meta: { limit: 100, next_cursor: null, has_more: false, total: 1 },
    });
    setupJobs([givenJobRow({ location: "Chingola Copperbelt" })]);
    render(<JobMatchingPage />);

    // GIVEN the user has selected a specific location
    await checkLocationOption("Copperbelt");
    await waitFor(() => {
      expect((useJobs as jest.Mock).mock.calls.at(-1)?.[0]?.location).toEqual(["Copperbelt"]);
    });

    // WHEN the user checks "All"
    const allOption = await screen.findByRole("menuitemcheckbox", { name: "All" });
    fireEvent.click(allOption);

    // THEN no location filter is sent to the backend
    await waitFor(() => {
      expect((useJobs as jest.Mock).mock.calls.at(-1)?.[0]?.location).toEqual([]);
    });
  });
});

describe("JobMatchingPage Matched for You filters", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [],
      meta: { limit: 20, next_cursor: null, has_more: false, total: 0 },
    });
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue({ id: GIVEN_USER_ID });
  });

  const switchToMatchedTab = async () => {
    fireEvent.click(await screen.findByRole("tab", { name: "Matched for You" }));
  };

  test("should filter the matched jobs shown by the selected category, entirely client-side", async () => {
    // GIVEN the Matched for You tab has jobs from two different categories
    setupJobs([]);
    setupMatchedJobs([
      givenJobRow({ id: "1", jobTitle: "Engineer Role", category: "Engineering" }),
      givenJobRow({ id: "2", jobTitle: "Sales Role", category: "Sales" }),
    ]);
    render(<JobMatchingPage />);
    await switchToMatchedTab();
    expect(await screen.findByText("Engineer Role")).toBeInTheDocument();
    expect(screen.getByText("Sales Role")).toBeInTheDocument();

    // WHEN the user filters the Matched tab by the "Engineering" category
    await selectFilterOption("category", "Engineering");

    // THEN only the matching row remains, without any refetch (getMatchedJobs is never
    // called with filter args — GET /jobs/matched doesn't accept any)
    await waitFor(() => expect(screen.queryByText("Sales Role")).not.toBeInTheDocument());
    expect(screen.getByText("Engineer Role")).toBeInTheDocument();
    expect(JobService.getInstance().getMatchedJobs as jest.Mock).not.toHaveBeenCalled();
  });

  test("should never call GET /jobs/matched, no matter how many filters are toggled on the Matched tab", async () => {
    // GIVEN the Matched for You tab is active
    setupJobs([]);
    setupMatchedJobs([
      givenJobRow({
        id: "1",
        jobTitle: "Engineer Role",
        category: "Engineering",
        employmentType: "full time",
        location: "Lusaka Lusaka",
      }),
      givenJobRow({
        id: "2",
        jobTitle: "Sales Role",
        category: "Sales",
        employmentType: "part time",
        location: "Ndola Copperbelt",
      }),
    ]);
    render(<JobMatchingPage />);
    await switchToMatchedTab();
    expect(await screen.findByText("Engineer Role")).toBeInTheDocument();

    // WHEN the user toggles category, then type, then a location, one after another
    await selectFilterOption("category", "Engineering");
    await waitFor(() => expect(screen.queryByText("Sales Role")).not.toBeInTheDocument());

    await selectFilterOption("category", "All");
    expect(await screen.findByText("Sales Role")).toBeInTheDocument();

    await selectFilterOption("employmentType", "Full Time");
    await waitFor(() => expect(screen.queryByText("Sales Role")).not.toBeInTheDocument());

    await selectFilterOption("employmentType", "All");
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await checkLocationOption("Lusaka");
    await waitFor(() => expect(screen.queryByText("Sales Role")).not.toBeInTheDocument());

    // THEN GET /jobs/matched was never called — Browse Jobs is the only tab that talks to the
    // backend for filtering; Matched for You only ever filters client-side
    expect(JobService.getInstance().getMatchedJobs as jest.Mock).not.toHaveBeenCalled();
  });

  test("should filter the matched jobs by location token independently of the Browse Jobs filter", async () => {
    // GIVEN matched jobs in two different locations
    setupJobs([]);
    setupMatchedJobs([
      givenJobRow({ id: "1", jobTitle: "Lusaka Role", location: "Lusaka Lusaka" }),
      givenJobRow({ id: "2", jobTitle: "Ndola Role", location: "Ndola Copperbelt" }),
    ]);
    render(<JobMatchingPage />);
    await switchToMatchedTab();
    expect(await screen.findByText("Lusaka Role")).toBeInTheDocument();

    // WHEN the user checks the "Ndola" token in the Matched tab's location filter
    await checkLocationOption("Ndola");

    // THEN only the Ndola row remains
    await waitFor(() => expect(screen.queryByText("Lusaka Role")).not.toBeInTheDocument());
    expect(screen.getByText("Ndola Role")).toBeInTheDocument();

    // close the filter popover before navigating away
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    // AND switching back to Browse Jobs is unaffected by the Matched tab's filter selection
    fireEvent.click(await screen.findByRole("tab", { name: "Browse Jobs" }));
    const lastBrowseCallArgs = (useJobs as jest.Mock).mock.calls.at(-1)?.[0];
    expect(lastBrowseCallArgs?.location).toEqual([]);
  });

  test("should match a multi-word province by either of its words, since the combined location string has no reliable word boundary", async () => {
    // GIVEN a matched job whose combined location is "city + two-word province" with
    // nothing marking where the city ends and the province begins
    setupJobs([]);
    setupMatchedJobs([
      givenJobRow({ id: "1", jobTitle: "Zambezi Role", location: "Zambezi North Western" }),
      givenJobRow({ id: "2", jobTitle: "Unrelated Role", location: "Lusaka Lusaka" }),
    ]);
    render(<JobMatchingPage />);
    await switchToMatchedTab();
    expect(await screen.findByText("Zambezi Role")).toBeInTheDocument();

    // WHEN the user checks "Western" — the second half of the two-word province, not a
    // standalone place name on its own
    await checkLocationOption("Western");

    // THEN the Zambezi job still matches (its location string contains "Western"), even
    // though "Western" alone was never a correctly-segmented token
    await waitFor(() => expect(screen.queryByText("Unrelated Role")).not.toBeInTheDocument());
    expect(screen.getByText("Zambezi Role")).toBeInTheDocument();
  });
});

describe("JobMatchingPage active filter chips", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (JobService.getInstance().listJobs as jest.Mock).mockResolvedValue({
      data: [
        {
          uuid: "1",
          location: "Chingola Copperbelt",
          city: "Chingola",
          province: "Copperbelt",
          category: "Technology",
          employment_type: "full time",
        },
      ],
      meta: { limit: 100, next_cursor: null, has_more: false, total: 1 },
    });
    (AuthenticationStateService.getInstance().getUser as jest.Mock).mockReturnValue({ id: GIVEN_USER_ID });
  });

  test("should show no chips when no filter is active", async () => {
    setupJobs([givenJobRow()]);
    setupMatchedJobs([]);
    render(<JobMatchingPage />);
    await screen.findByText("Software Engineer");

    expect(screen.queryByText(/^Category:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Type:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Location:/)).not.toBeInTheDocument();
  });

  test("should show a removable chip for each active Browse Jobs filter, including one per selected location", async () => {
    setupJobs([givenJobRow()]);
    setupMatchedJobs([]);
    render(<JobMatchingPage />);
    await screen.findByText("Software Engineer");

    // WHEN the user selects a category, a type, and two locations
    await selectFilterOption("category", "Technology");
    await selectFilterOption("employmentType", "Full Time");
    await checkLocationOption("Copperbelt");
    await checkLocationOption("Chingola");
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    // THEN a chip appears for each active filter, one per selected location
    expect(await screen.findByText("Category: Technology")).toBeInTheDocument();
    expect(screen.getByText("Type: Full Time")).toBeInTheDocument();
    expect(screen.getByText("Location: Copperbelt")).toBeInTheDocument();
    expect(screen.getByText("Location: Chingola")).toBeInTheDocument();
  });

  test("should clear just that filter when a chip's remove button is clicked", async () => {
    setupJobs([givenJobRow()]);
    setupMatchedJobs([]);
    render(<JobMatchingPage />);
    await screen.findByText("Software Engineer");

    await selectFilterOption("category", "Technology");
    const chip = await screen.findByText("Category: Technology");

    // WHEN the chip's own remove ("x") control is clicked
    const removeButton = chip.parentElement?.querySelector('[data-testid="CancelIcon"]');
    expect(removeButton).toBeTruthy();
    fireEvent.click(removeButton!);

    // THEN the chip disappears and the Browse Jobs query is re-run without that category
    await waitFor(() => expect(screen.queryByText("Category: Technology")).not.toBeInTheDocument());
    await waitFor(() => {
      const lastCallArgs = (useJobs as jest.Mock).mock.calls.at(-1)?.[0];
      expect(lastCallArgs?.category).toBe("all");
    });
  });

  test("should track Matched for You's filter chips independently of Browse Jobs", async () => {
    setupJobs([givenJobRow()]);
    setupMatchedJobs([givenJobRow({ id: "m1", jobTitle: "Matched Role", category: "Sales" })]);
    render(<JobMatchingPage />);
    await screen.findByText("Software Engineer");

    // WHEN a category filter is applied on Browse Jobs only
    await selectFilterOption("category", "Technology");
    expect(await screen.findByText("Category: Technology")).toBeInTheDocument();

    // AND the user switches to Matched for You
    fireEvent.click(await screen.findByRole("tab", { name: "Matched for You" }));
    await screen.findByText("Matched Role");

    // THEN no chip carries over — Matched for You has its own, separately-tracked filter state
    expect(screen.queryByText("Category: Technology")).not.toBeInTheDocument();

    // WHEN the user filters the Matched tab by its own category
    await selectFilterOption("category", "Sales");
    expect(await screen.findByText("Category: Sales")).toBeInTheDocument();

    // AND switches back to Browse Jobs
    fireEvent.click(await screen.findByRole("tab", { name: "Browse Jobs" }));

    // THEN Browse Jobs' own chip is still there, unaffected by the Matched tab's filter
    expect(await screen.findByText("Category: Technology")).toBeInTheDocument();
    expect(screen.queryByText("Category: Sales")).not.toBeInTheDocument();
  });
});
