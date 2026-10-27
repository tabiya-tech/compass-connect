// mute the console
import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import React from "react";
import { render, screen } from "src/_test_utilities/test-utils";
import AuthPageShell, { DATA_TEST_ID } from "src/auth/components/AuthPageShell/AuthPageShell";
import { getDisabledModules } from "src/envService";

describe("AuthPageShell", () => {
  beforeEach(() => {
    (getDisabledModules as jest.Mock).mockReturnValue([]);
  });

  test("should show the help button when the help page is enabled", () => {
    // GIVEN no module is disabled
    // WHEN the shell is rendered
    render(<AuthPageShell logoUrl="/logo.svg" />);

    // THEN the help button is shown
    expect(screen.getByTestId(DATA_TEST_ID.AUTH_PAGE_SHELL_FAQ_BUTTON)).toBeInTheDocument();
  });

  test("should not show the help button when the help page is disabled", () => {
    // GIVEN the help page is disabled
    (getDisabledModules as jest.Mock).mockReturnValue(["faq"]);

    // WHEN the shell is rendered
    render(<AuthPageShell logoUrl="/logo.svg" />);

    // THEN the help button is not shown
    expect(screen.queryByTestId(DATA_TEST_ID.AUTH_PAGE_SHELL_FAQ_BUTTON)).not.toBeInTheDocument();
  });
});
