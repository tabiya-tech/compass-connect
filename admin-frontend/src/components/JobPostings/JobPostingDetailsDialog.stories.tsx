import type { Meta, StoryObj } from "@storybook/react";
import JobPostingDetailsDialog from "src/components/JobPostings/JobPostingDetailsDialog";
import type { JobPostingRow } from "src/types";

const meta: Meta<typeof JobPostingDetailsDialog> = {
  title: "Dashboard/JobPostings/DetailsDialog",
  component: JobPostingDetailsDialog,
  tags: ["autodocs"],
};

export default meta;

type Story = StoryObj<typeof JobPostingDetailsDialog>;

const storyJobPostingFixture: JobPostingRow = {
  id: "job-1",
  jobTitle: "Junior Software Developer",
  sector: "ICT",
  contractType: "full_time",
  location: "Lusaka",
  platform: "BrighterMonday",
  jobUrl: "https://example.com/jobs/junior-software-developer",
};

export const Shown: Story = {
  args: {
    job: storyJobPostingFixture,
    isOpen: true,
    onClose: () => {},
  },
  render: (args) => <JobPostingDetailsDialog {...args} />,
};
