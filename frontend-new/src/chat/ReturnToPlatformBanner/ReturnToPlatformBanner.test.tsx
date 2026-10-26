import "src/_test_utilities/consoleMock";

import React from "react";
import { render, screen } from "src/_test_utilities/test-utils";
import userEvent from "@testing-library/user-event";
import ReturnToPlatformBanner, { DATA_TEST_ID, getReturnSite } from "./ReturnToPlatformBanner";

describe("ReturnToPlatformBanner", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    // window.location.assign cannot be spied on in jsdom, so replace location for these tests
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: jest.fn() },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  test("should show a button back to the site of the return url", () => {
    // GIVEN a return url
    const givenReturnUrl = "https://partner.example.org/perfil?vuelta=1";

    // WHEN the banner is rendered
    render(<ReturnToPlatformBanner returnUrl={givenReturnUrl} />);

    // THEN the banner is shown
    expect(screen.getByTestId(DATA_TEST_ID.CONTAINER)).toBeInTheDocument();
    // AND the button names the site
    expect(screen.getByTestId(DATA_TEST_ID.BUTTON)).toHaveTextContent("partner.example.org");
    // AND no errors or warnings occurred
    expect(console.error).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  test("should send the user to the return url in the same tab when the button is clicked", async () => {
    // GIVEN the banner with a return url
    const givenReturnUrl = "https://partner.example.org/perfil?vuelta=1";
    render(<ReturnToPlatformBanner returnUrl={givenReturnUrl} />);

    // WHEN the user clicks the button
    await userEvent.click(screen.getByTestId(DATA_TEST_ID.BUTTON));

    // THEN the browser goes to the return url
    expect(window.location.assign).toHaveBeenCalledWith(givenReturnUrl);
  });

  test("should render nothing for a return url that must not be followed", () => {
    // WHEN the banner is rendered with a javascript: url
    // eslint-disable-next-line no-script-url -- a URL that must be refused
    render(<ReturnToPlatformBanner returnUrl={"javascript:alert(1)"} />);

    // THEN nothing is shown
    expect(screen.queryByTestId(DATA_TEST_ID.CONTAINER)).not.toBeInTheDocument();
  });

  describe("getReturnSite", () => {
    test.each([
      ["https://partner.example.org/perfil", "partner.example.org"],
      ["http://localhost:3100/return", "localhost"],
    ])("should return the hostname of %s", (givenUrl, expectedSite) => {
      expect(getReturnSite(givenUrl)).toBe(expectedSite);
    });

    test.each([
      // eslint-disable-next-line no-script-url -- a URL that must be refused
      ["javascript:alert(1)"],
      ["data:text/html,hello"],
      ["not a url"],
      ["/relative/path"],
      [""],
      [null],
      [undefined],
    ])("should return null for %s", (givenUrl) => {
      expect(getReturnSite(givenUrl)).toBeNull();
    });
  });
});
