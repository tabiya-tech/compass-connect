import "src/_test_utilities/consoleMock";
import "src/_test_utilities/envServiceMock";

import React from "react";
import { render, screen, userEvent, within } from "src/_test_utilities/test-utils";
import ModuleCard, { DATA_TEST_ID } from "./ModuleCard";
import { Module, ModuleId } from "src/home/modulesService";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    __esModule: true,
    useNavigate: () => mockNavigate,
  };
});

const baseModule: Module = {
  id: ModuleId.SKILLS_DISCOVERY,
  labelKey: "home.modules.skillsDiscovery",
  descriptionKey: "home.modules.skillsDiscoveryDesc",
  route: "/skills-interests",
};

describe("ModuleCard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockNavigate.mockClear();
  });

  test("should render the card with title and description for a given module", () => {
    // GIVEN a module

    // WHEN the ModuleCard is rendered
    render(<ModuleCard module={baseModule} />);

    // THEN the card container is in the document
    const card = screen.getByTestId(DATA_TEST_ID.MODULE_CARD);
    expect(card).toBeInTheDocument();
    // AND the title is displayed
    expect(screen.getByTestId(DATA_TEST_ID.MODULE_CARD_TITLE)).toBeInTheDocument();
    // AND the description is displayed
    expect(screen.getByTestId(DATA_TEST_ID.MODULE_CARD_DESCRIPTION)).toBeInTheDocument();
    // AND the icon is displayed
    expect(screen.getByTestId(DATA_TEST_ID.MODULE_CARD_ICON)).toBeInTheDocument();
    // AND to match the snapshot
    expect(card).toMatchSnapshot();
  });

  test("should not show a badge when badgeStatus is null", () => {
    // GIVEN a skills_discovery module with no badge

    // WHEN the ModuleCard is rendered
    render(<ModuleCard module={baseModule} badgeStatus={null} />);

    // THEN no continue or completed chip is shown
    expect(screen.queryByTestId(DATA_TEST_ID.MODULE_CARD_CONTINUE_CHIP)).not.toBeInTheDocument();
    expect(screen.queryByTestId(DATA_TEST_ID.MODULE_CARD_COMPLETED_CHIP)).not.toBeInTheDocument();
  });

  test("should show continue badge when badgeStatus is continue and module is skills_discovery", () => {
    // GIVEN a skills_discovery module with continue badge

    // WHEN the ModuleCard is rendered
    render(<ModuleCard module={baseModule} badgeStatus="continue" />);

    // THEN the continued chip is shown
    expect(screen.getByTestId(DATA_TEST_ID.MODULE_CARD_CONTINUE_CHIP)).toBeInTheDocument();
  });

  test("should show completed badge when badgeStatus is completed and module is skills_discovery", () => {
    // GIVEN a skills_discovery module with completed badge

    // WHEN the ModuleCard is rendered
    render(<ModuleCard module={baseModule} badgeStatus="completed" />);

    // THEN the completed chip is shown
    expect(screen.getByTestId(DATA_TEST_ID.MODULE_CARD_COMPLETED_CHIP)).toBeInTheDocument();
  });

  test("should navigate to the module route when the card is clicked", async () => {
    // GIVEN a module with a route

    // WHEN the ModuleCard is rendered
    render(<ModuleCard module={baseModule} />);

    // AND the card is clicked
    const card = screen.getByTestId(DATA_TEST_ID.MODULE_CARD);
    const actionArea = within(card).getByRole("button");
    await userEvent.click(actionArea);

    // THEN it navigates to the module route
    expect(mockNavigate).toHaveBeenCalledWith(baseModule.route);
  });
});
