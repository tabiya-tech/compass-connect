// mute chatty console
import "src/_test_utilities/consoleMock";

import { render, screen, waitFor } from "src/_test_utilities/test-utils";
import LegalDocumentPage, { DATA_TEST_ID } from "src/legal/pages/LegalDocumentPage";
import * as legalDocumentLoader from "src/legal/legalDocumentLoader";
import { DATA_TEST_ID as BACKDROP_DATA_TEST_ID } from "src/theme/Backdrop/Backdrop";
import { DATA_TEST_ID as ERROR_PAGE_DATA_TEST_ID } from "src/error/errorPage/ErrorPage";

// mock the BugReportButton (dependency of ErrorPage)
jest.mock("src/feedback/bugReport/bugReportButton/BugReportButton", () => {
  const actual = jest.requireActual("src/feedback/bugReport/bugReportButton/BugReportButton");
  return {
    ...actual,
    __esModule: true,
    default: jest.fn().mockImplementation(() => {
      return <span data-testid={actual.DATA_TEST_ID.BUG_REPORT_BUTTON_CONTAINER}></span>;
    }),
  };
});

describe("LegalDocumentPage", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("renders the loading backdrop while the document is being fetched", () => {
    // GIVEN a loader that never resolves
    jest.spyOn(legalDocumentLoader, "getLegalDocument").mockReturnValue(new Promise(() => {}));

    // WHEN the page is rendered
    render(<LegalDocumentPage variant="termsOfUse" />);

    // THEN the backdrop is shown
    expect(screen.getByTestId(BACKDROP_DATA_TEST_ID.BACKDROP_CONTAINER)).toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.LEGAL_PAGE_CONTAINER)).not.toBeInTheDocument();
  });

  test("renders the document title and markdown body on a successful load", async () => {
    // GIVEN a loader that resolves with a document
    jest.spyOn(legalDocumentLoader, "getLegalDocument").mockResolvedValue({
      title: "Terms of Use",
      markdown: "# Hello",
    });

    // WHEN the page is rendered
    render(<LegalDocumentPage variant="termsOfUse" />);

    // THEN the document body and title appear once loading completes
    await waitFor(() => {
      expect(screen.getByTestId(DATA_TEST_ID.LEGAL_PAGE_CONTAINER)).toBeInTheDocument();
    });
    expect(screen.getByTestId(DATA_TEST_ID.LEGAL_PAGE_TITLE)).toHaveTextContent("Terms of Use");
    expect(screen.getByTestId(DATA_TEST_ID.LEGAL_PAGE_BODY)).toBeInTheDocument();
  });

  test("renders the error page when the loader rejects", async () => {
    // GIVEN a loader that rejects
    jest.spyOn(legalDocumentLoader, "getLegalDocument").mockRejectedValue(new Error("boom"));

    // WHEN the page is rendered
    render(<LegalDocumentPage variant="privacyPolicy" />);

    // THEN the error page is shown
    await waitFor(() => {
      expect(screen.getByTestId(ERROR_PAGE_DATA_TEST_ID.ERROR_CONTAINER)).toBeInTheDocument();
    });
    expect(screen.queryByTestId(DATA_TEST_ID.LEGAL_PAGE_CONTAINER)).not.toBeInTheDocument();
  });
});
