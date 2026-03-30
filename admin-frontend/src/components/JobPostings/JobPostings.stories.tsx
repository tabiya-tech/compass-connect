import type { Meta, StoryObj } from "@storybook/react";
import JobPostings from "src/components/JobPostings/JobPostings";
import type { JobPostingRow, JobPostingStats } from "src/types";

const meta: Meta<typeof JobPostings> = {
  title: "Dashboard/JobPostings",
  component: JobPostings,
  tags: ["autodocs"],
};

export default meta;

type Story = StoryObj<typeof JobPostings>;

const rows: JobPostingRow[] = [
  {
    id: "job-1",
    jobTitle: "Junior Software Developer",
    sector: "ICT",
    contractType: "full_time",
    location: "Lusaka",
    platform: "BrighterMonday",
    jobUrl: "https://example.com/jobs/junior-software-developer",
  },
  {
    id: "job-2",
    jobTitle: "Electrical Technician",
    sector: "Energy",
    contractType: "full_time",
    location: "Ndola",
    platform: "GoZ Jobs",
    jobUrl: "https://example.com/jobs/electrical-technician",
  },
];

const stats: JobPostingStats = {
  jobsSourced: rows.length,
  sectorsCovered: 2,
  sourcePlatformsCount: 2,
};

export const Shown: Story = {
  args: {
    rows,
    stats,
  },
};
