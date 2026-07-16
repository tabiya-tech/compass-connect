import React from "react";
import { Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import Papa from "papaparse";
import { useTranslation } from "react-i18next";
import { getModuleLabelKey, PLACEHOLDER_SYMBOL } from "src/constants";
import { useInstructorStudentsTableState, type StudentsSortKey } from "src/hooks/useInstructorStudentsTableState";
import type { InstructorStudentRow } from "src/types";
import DataTable, { type ColumnDef } from "src/components/DataTable/DataTable";

export interface InstructorStudentsTableProps {
  rows: InstructorStudentRow[];
  loading?: boolean;
  hasMoreRows?: boolean;
  onLoadMoreRows?: () => Promise<void>;
}

interface CsvColumn<T> {
  header: string;
  getValue: (row: T) => string | number | null | undefined;
}

const downloadCsvFile = (filename: string, csvContent: string): void => {
  const blob = new Blob([`﻿${csvContent}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const fracComplete = (s: string): boolean => {
  const m = s.trim().match(/^(\d+)\s*\/\s*(\d+)$/);
  return !!m && m[1] === m[2] && +m[2] > 0;
};

const checkIconSx = { color: "secondary.main", fontSize: 22 } as const;

const InstructorStudentsTable: React.FC<InstructorStudentsTableProps> = ({
  rows: allRows,
  loading = false,
  hasMoreRows = false,
  onLoadMoreRows,
}) => {
  const { t } = useTranslation();

  const {
    sortKey,
    sortDir,
    handleSort,
    clearSort,
    nameSearch,
    setNameSearch,
    programme,
    setProgramme,
    yearFilter,
    setYearFilter,
    lastLoginFilter,
    setLastLoginFilter,
    lastModuleFilter,
    setLastModuleFilter,
    treatmentGroupFilter,
    setTreatmentGroupFilter,
    programmes,
    years,
    modules,
    treatmentGroups,
    filteredRows,
    sortedRows,
    pagedRows,
    pageSize,
    totalItems,
    totalPages,
    safePageIndex,
    goToPage,
  } = useInstructorStudentsTableState(allRows, {
    hasMoreRows,
    loadingRows: loading,
    onLoadMoreRows,
  });

  const allLabel = t("instructorDashboard.studentsTable.filters.all");
  const currentPage = safePageIndex + 1;
  const rangeStart = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const rangeEnd = totalItems === 0 ? 0 : Math.min(currentPage * pageSize, totalItems);
  const pageLabel = t("dashboard.pagination.range", { start: rangeStart, end: rangeEnd, total: totalItems });

  const formatModuleLabel = (moduleId: string) => {
    const key = getModuleLabelKey(moduleId);
    return key ? t(key) : PLACEHOLDER_SYMBOL;
  };

  const handleDownloadCsv = () => {
    const csvColumns: CsvColumn<InstructorStudentRow>[] = [
      { header: t("instructorDashboard.studentsTable.headers.id"), getValue: (row) => row.id },
      { header: t("instructorDashboard.studentsTable.headers.studentName"), getValue: (row) => row.studentName },
      { header: t("instructorDashboard.studentsTable.headers.programme"), getValue: (row) => row.programme },
      {
        header: t("instructorDashboard.studentsTable.headers.qualificationType"),
        getValue: (row) => row.qualificationType,
      },
      { header: t("instructorDashboard.studentsTable.headers.year"), getValue: (row) => row.year },
      { header: t("instructorDashboard.studentsTable.headers.gender"), getValue: (row) => row.gender },
      ...(treatmentGroups.length > 0
        ? [
            {
              header: t("instructorDashboard.studentsTable.headers.treatmentGroup"),
              getValue: (row: InstructorStudentRow) => row.treatmentGroup ?? "",
            },
          ]
        : []),
      { header: t("instructorDashboard.studentsTable.headers.lastLogin"), getValue: (row) => row.lastLogin },
      {
        header: t("instructorDashboard.studentsTable.headers.lastActiveModule"),
        getValue: (row) => formatModuleLabel(row.lastActiveModuleId),
      },
      {
        header: t("instructorDashboard.studentsTable.headers.careerReadinessStarted"),
        getValue: (row) => row.careerReadinessStarted,
      },
      {
        header: t("instructorDashboard.studentsTable.headers.careerReadinessCompleted"),
        getValue: (row) => row.careerReadinessCompleted,
      },
      {
        header: t("instructorDashboard.studentsTable.headers.skillsInterestsExplored"),
        getValue: (row) => t(`instructorDashboard.studentsTable.statusLabels.${row.skillsDiscoveryStatus}`),
      },
      {
        header: t("instructorDashboard.studentsTable.headers.careerExplorer"),
        getValue: (row) =>
          row.careerExplorerMessagesSent !== null && row.careerExplorerMessagesSent >= 2
            ? t("instructorDashboard.studentsTable.statusLabels.started")
            : t("instructorDashboard.studentsTable.statusLabels.not_started"),
      },
    ];

    const csv = Papa.unparse({
      fields: csvColumns.map((column) => column.header),
      data: sortedRows.map((row) =>
        csvColumns.map((column) => {
          const value = column.getValue(row);
          return value === null || value === undefined ? "" : String(value);
        })
      ),
    });
    const date = new Date().toISOString().slice(0, 10);
    downloadCsvFile(`students_export_${date}.csv`, csv);
  };

  const columns: ColumnDef<InstructorStudentRow>[] = [
    {
      key: "studentName",
      label: t("instructorDashboard.studentsTable.headers.studentName").toUpperCase(),
      sortable: true,
      sortType: "text",
      align: "center",
      render: (val) => (
        <Typography
          variant="body2"
          noWrap
          title={val as string}
          sx={{ fontWeight: 700, color: "info.main", textAlign: "center", width: "100%" }}
        >
          {val as string}
        </Typography>
      ),
    },
    {
      key: "programme",
      label: t("instructorDashboard.studentsTable.headers.programme").toUpperCase(),
      sortable: true,
      sortType: "text",
      align: "center",
      filter: {
        options: programmes.map((p) => ({ value: p, label: p === "all" ? allLabel : p })),
        value: programme,
        onChange: setProgramme,
      },
      render: (val, row) => (
        <Typography variant="body2" noWrap title={row.programme} sx={{ textAlign: "center", width: "100%" }}>
          {row.programme}
        </Typography>
      ),
    },
    {
      key: "qualificationType",
      label: t("instructorDashboard.studentsTable.headers.qualificationType").toUpperCase(),
      sortable: true,
      sortType: "text",
      align: "center",
      render: (val, row) => (
        <Typography variant="body2" noWrap title={row.qualificationType} sx={{ textAlign: "center", width: "100%" }}>
          {row.qualificationType}
        </Typography>
      ),
    },
    {
      key: "year",
      label: t("instructorDashboard.studentsTable.headers.year").toUpperCase(),
      sortable: true,
      sortType: "number",
      align: "center",
      filter: {
        options: years.map((y) => ({ value: y, label: y === "all" ? allLabel : y })),
        value: yearFilter,
        onChange: setYearFilter,
      },
      render: (val, row) => <span style={{ textAlign: "center", display: "block", width: "100%" }}>{row.year}</span>,
    },
    // Only surface the treatment group column/filter when at least one student is assigned to a group.
    ...(treatmentGroups.length > 0
      ? [
          {
            key: "treatmentGroup" as const,
            label: t("instructorDashboard.studentsTable.headers.treatmentGroup").toUpperCase(),
            sortable: true,
            sortType: "text" as const,
            align: "center" as const,
            filter: {
              options: [
                { value: "all", label: allLabel },
                ...treatmentGroups.map((group) => ({ value: group, label: group })),
              ],
              value: treatmentGroupFilter,
              onChange: setTreatmentGroupFilter,
            },
            render: (_val: unknown, row: InstructorStudentRow) => {
              const label = row.treatmentGroup ?? PLACEHOLDER_SYMBOL;
              return (
                <Typography variant="body2" noWrap title={label} sx={{ textAlign: "center", width: "100%" }}>
                  {label}
                </Typography>
              );
            },
          },
        ]
      : []),
    {
      key: "lastLogin",
      label: t("instructorDashboard.studentsTable.headers.lastLogin").toUpperCase(),
      sortable: true,
      sortType: "number",
      align: "center",
      filter: {
        options: [
          { value: "all", label: allLabel },
          { value: "today", label: t("instructorDashboard.studentsTable.filters.today") },
          { value: "week", label: t("instructorDashboard.studentsTable.filters.thisWeek") },
          { value: "older", label: t("instructorDashboard.studentsTable.filters.older") },
        ],
        value: lastLoginFilter,
        onChange: setLastLoginFilter,
      },
      render: (val) => (
        <Typography variant="body2" noWrap title={val as string} sx={{ textAlign: "center", width: "100%" }}>
          {val as string}
        </Typography>
      ),
    },
    {
      key: "lastActiveModuleId",
      label: t("instructorDashboard.studentsTable.headers.lastActiveModule").toUpperCase(),
      sortable: true,
      sortType: "text",
      align: "center",
      filter: {
        options: modules.map((m) => ({
          value: m,
          label: m === "all" ? allLabel : formatModuleLabel(m),
        })),
        value: lastModuleFilter,
        onChange: setLastModuleFilter,
      },
      render: (val, row) => {
        const label = formatModuleLabel(row.lastActiveModuleId);
        return (
          <Typography variant="body2" noWrap title={label} sx={{ textAlign: "center", width: "100%" }}>
            {label}
          </Typography>
        );
      },
    },
    {
      key: "careerReadinessStarted",
      label: t("instructorDashboard.studentsTable.headers.careerReadinessStarted"),
      sortable: true,
      sortType: "number",
      align: "center",
      minWidth: 130,
    },
    {
      key: "skillsDiscoveryStatus",
      label: t("instructorDashboard.studentsTable.headers.skillsInterestsExplored"),
      sortable: true,
      sortType: "text",
      align: "center",
      minWidth: 130,
      render: (_val, row) => {
        const labelKey = `instructorDashboard.studentsTable.statusLabels.${row.skillsDiscoveryStatus}`;
        return (
          <Typography variant="body2" sx={{ textAlign: "center", width: "100%" }}>
            {t(labelKey)}
          </Typography>
        );
      },
    },
    {
      key: "careerExplorerMessagesSent",
      label: t("instructorDashboard.studentsTable.headers.careerExplorer"),
      sortable: true,
      sortType: "number",
      align: "center",
      minWidth: 130,
      render: (_val, row) => {
        const label =
          row.careerExplorerMessagesSent !== null && row.careerExplorerMessagesSent >= 2
            ? t("instructorDashboard.studentsTable.statusLabels.started")
            : t("instructorDashboard.studentsTable.statusLabels.not_started");
        return (
          <Typography variant="body2" sx={{ textAlign: "center", width: "100%" }}>
            {label}
          </Typography>
        );
      },
    },
    {
      key: "careerReadinessCompleted",
      label: t("instructorDashboard.studentsTable.headers.careerReadinessCompleted"),
      sortable: true,
      sortType: "text",
      align: "center",
      minWidth: 130,
      render: (val) => (fracComplete(val as string) ? <CheckCircleIcon sx={checkIconSx} /> : (val as string)),
    },
  ];

  return (
    <DataTable<InstructorStudentRow>
      rows={pagedRows}
      columns={columns}
      loading={loading}
      search={{
        placeholder: t("instructorDashboard.studentsTable.filters.searchPlaceholder"),
        ariaLabel: t("instructorDashboard.studentsTable.filters.searchAriaLabel"),
        value: nameSearch,
        onChange: setNameSearch,
      }}
      exportButton={{
        label: t("instructorDashboard.studentsTable.downloadCsv"),
        onExport: handleDownloadCsv,
        disabled: loading || sortedRows.length === 0,
      }}
      skeletonRows={8}
      emptyMessage={filteredRows.length === 0 ? t("instructorDashboard.studentsTable.empty") : undefined}
      ariaLabel={t("instructorDashboard.studentsTable.ariaLabel")}
      externalSortKey={sortKey as keyof InstructorStudentRow | null}
      externalSortDir={sortDir}
      onSortChange={(key, dir) => handleSort(key as StudentsSortKey, dir)}
      onSortClear={clearSort}
      sortClearLabel={t("dashboard.dataTable.clearSorting")}
      page={currentPage}
      totalPages={totalPages}
      onPageChange={goToPage}
      prevPageLabel={t("dashboard.institutionsTable.prevPage")}
      nextPageLabel={t("dashboard.institutionsTable.nextPage")}
      pageLabel={pageLabel}
    />
  );
};

export default InstructorStudentsTable;
