// mute the console
import "src/_test_utilities/consoleMock";

import { render, screen } from "src/_test_utilities/test-utils";
import BWSTaskMessage from "src/chat/chatMessage/bwsTaskMessage/BWSTaskMessage";
import i18n from "src/i18n/i18n";

describe("BWSTaskMessage", () => {
  test("should show the task progress from the translations", () => {
    // GIVEN a BWS task that is the 2nd of 8 tasks
    const givenProps = {
      taskId: "task-2",
      taskNumber: 2,
      totalTasks: 8,
      alternatives: [
        { wa_id: "wa-1", label: "Teach and train people" },
        { wa_id: "wa-2", label: "Lead and motivate your team" },
      ],
      onSubmit: jest.fn(),
    };

    // WHEN the BWS task is rendered
    render(<BWSTaskMessage {...givenProps} />);

    // THEN the progress text comes from the translations, with the task number and total filled in
    const expectedProgress = i18n.t("chat.chatMessage.bwsTaskMessage.progress", { taskNumber: 2, totalTasks: 8 });
    expect(expectedProgress).toBe("2 of 8");
    expect(screen.getByText(expectedProgress)).toBeInTheDocument();
  });
});
