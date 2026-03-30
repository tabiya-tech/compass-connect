import React, { useMemo, useState } from "react";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import { Box, Button, Grid, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import JobPostingDetailsDialog from "src/components/JobPostings/JobPostingDetailsDialog";
import StatCard from "src/components/StatCard/StatCard";
import DataTable from "src/components/DataTable/DataTable";
import type { ColumnDef } from "src/components/DataTable/DataTable";
import type { JobPostingRow } from "src/types";
import { useJobPostings } from "src/hooks/useJobPostings";

const capitalize = (s: string) =>
  (s ?? "")
    .toLowerCase()
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

const uniqueOptions = (rows: JobPostingRow[], key: keyof JobPostingRow) => {
  const values = Array.from(new Set(rows.map((r) => String(r[key] ?? "")).filter(Boolean))).sort();
  return [{ value: "all", label: "All" }, ...values.map((v) => ({ value: v, label: capitalize(v) }))];
};

const JobPostings: React.FC = () => {
  const theme = useTheme();
  const { t } = useTranslation();
  const {
    rows: jobPostings,
    stats: jobPostingStats,
    loading,
    error,
    hasNextPage,
    hasPrevPage,
    page,
    goToNextPage,
    goToPrevPage,
  } = useJobPostings();

  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("all");
  const [locationFilter, setLocationFilter] = useState("all");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [selectedJob, setSelectedJob] = useState<JobPostingRow | null>(null);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return jobPostings.filter((row) => {
      const matchesSearch = !q || row.jobTitle.toLowerCase().includes(q);
      const matchesSector = sectorFilter === "all" || row.sector === sectorFilter;
      const matchesLocation = locationFilter === "all" || row.location === locationFilter;
      const matchesPlatform = platformFilter === "all" || row.platform === platformFilter;
      return matchesSearch && matchesSector && matchesLocation && matchesPlatform;
    });
  }, [jobPostings, search, sectorFilter, locationFilter, platformFilter]);

  const columns: ColumnDef<JobPostingRow>[] = useMemo(
    () => [
      {
        key: "jobTitle",
        label: t("dashboard.jobPostings.table.jobTitle"),
        align: "left",
        minWidth: 180,
        render: (val) => <span style={{ fontWeight: 700 }}>{capitalize(val)}</span>,
      },
      {
        key: "sector",
        label: t("dashboard.jobPostings.table.sector"),
        align: "left",
        minWidth: 130,
        filter: {
          options: uniqueOptions(jobPostings, "sector"),
          value: sectorFilter,
          onChange: setSectorFilter,
        },
        render: (val) => capitalize(val),
      },
      {
        key: "contractType",
        label: t("dashboard.jobPostings.table.contractType"),
        align: "left",
        minWidth: 110,
        render: (val) => {
          const key = `dashboard.jobPostings.contractTypes.${val}`;
          const translated = t(key);
          return translated !== key ? translated : capitalize(val);
        },
      },
      {
        key: "location",
        label: t("dashboard.jobPostings.table.location"),
        align: "left",
        minWidth: 110,
        filter: {
          options: uniqueOptions(jobPostings, "location"),
          value: locationFilter,
          onChange: setLocationFilter,
        },
        render: (val) => capitalize(val),
      },
      {
        key: "platform",
        label: t("dashboard.jobPostings.table.platform"),
        align: "left",
        minWidth: 110,
        filter: {
          options: uniqueOptions(jobPostings, "platform"),
          value: platformFilter,
          onChange: setPlatformFilter,
        },
        render: (val) => capitalize(val),
      },
      {
        key: "jobUrl",
        label: t("dashboard.jobPostings.table.link"),
        align: "center",
        minWidth: 60,
        sortable: false,
        render: (val, row) =>
          val ? (
            <Button
              component="a"
              href={val}
              target="_blank"
              rel="noopener noreferrer"
              color="primary"
              variant="text"
              size="small"
              sx={{ minWidth: 0, p: 0.5 }}
              aria-label={t("dashboard.jobPostings.aria.openJob", { title: row.jobTitle })}
            >
              <OpenInNewOutlinedIcon fontSize="small" />
            </Button>
          ) : null,
      },
    ],
    [jobPostings, sectorFilter, locationFilter, platformFilter, t]
  );

  return (
    <Box sx={{ paddingBottom: theme.fixedSpacing(theme.tabiyaSpacing.lg) }}>
      <Grid container spacing={theme.fixedSpacing(theme.tabiyaSpacing.md)} sx={{ marginBottom: 2 }}>
        <Grid size={{ xs: 12, md: 4 }}>
          <StatCard
            title={t("dashboard.jobPostings.stats.jobsSourced")}
            value={jobPostingStats.jobsSourced}
            subtitle={t("dashboard.jobPostings.stats.lastUpdated")}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <StatCard title={t("dashboard.jobPostings.stats.sectorsCovered")} value={jobPostingStats.sectorsCovered} />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <StatCard
            title={t("dashboard.jobPostings.stats.sourcePlatforms")}
            value={jobPostingStats.sourcePlatformsCount}
            subtitle={t("dashboard.jobPostings.stats.sourcePlatformsList")}
          />
        </Grid>
      </Grid>

      {error && <Box sx={{ color: "error.main", mb: 1, fontSize: "0.85rem" }}>{error.message}</Box>}

      <DataTable<JobPostingRow>
        rows={filteredRows}
        columns={columns}
        loading={loading}
        skeletonRows={8}
        ariaLabel={t("dashboard.jobPostings.aria.table")}
        emptyMessage={t("dashboard.jobPostings.jobsCount", { count: 0, total: 0 })}
        tableMinWidth={750}
        search={{
          placeholder: t("dashboard.jobPostings.searchPlaceholder"),
          ariaLabel: t("dashboard.jobPostings.aria.search"),
          value: search,
          onChange: setSearch,
        }}
        page={page}
        hasNextPage={hasNextPage}
        hasPrevPage={hasPrevPage}
        onNextPage={goToNextPage}
        onPrevPage={goToPrevPage}
        pageLabel={`Page ${page}`}
      />

      <JobPostingDetailsDialog job={selectedJob} isOpen={Boolean(selectedJob)} onClose={() => setSelectedJob(null)} />
    </Box>
  );
};

export default JobPostings;
