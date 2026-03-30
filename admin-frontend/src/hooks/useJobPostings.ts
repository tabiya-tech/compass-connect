import { useCallback, useEffect, useState } from "react";
import AnalyticsService from "src/analytics/AnalyticsService";
import type { JobPostingRow, JobPostingStats } from "src/types";

const PAGE_SIZE = 20;

let _counter = 0;
const nextId = () => String(++_counter);

function mapToRow(doc: import("src/analytics/AnalyticsService.types").JobApiItem): JobPostingRow {
  return {
    id: nextId(),
    jobTitle: doc.opportunity_title ?? "",
    sector: doc.category ?? "",
    contractType: doc.contract_type ?? "",
    location: doc.location ?? "",
    platform: doc.source_platform ?? "",
    jobUrl: doc.URL ?? "",
  };
}

export interface UseJobPostingsResult {
  rows: JobPostingRow[];
  stats: JobPostingStats;
  loading: boolean;
  statsLoading: boolean;
  error: Error | null;
  hasNextPage: boolean;
  hasPrevPage: boolean;
  page: number;
  goToNextPage: () => void;
  goToPrevPage: () => void;
}

export function useJobPostings(): UseJobPostingsResult {
  const [cursorStack, setCursorStack] = useState<(string | undefined)[]>([undefined]);
  const [pageIndex, setPageIndex] = useState(0);
  const [rows, setRows] = useState<JobPostingRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [stats, setStats] = useState<JobPostingStats>({ jobsSourced: 0, sectorsCovered: 0, sourcePlatformsCount: 0 });
  const [statsLoading, setStatsLoading] = useState(true);

  // Fetch stats once
  useEffect(() => {
    let isMounted = true;
    setStatsLoading(true);
    AnalyticsService.getInstance()
      .getJobStats()
      .then((data) => {
        if (!isMounted) return;
        setStats({ jobsSourced: data.total, sectorsCovered: data.sectors, sourcePlatformsCount: data.platforms });
      })
      .catch(() => {
        /* stats are non-critical, silently ignore */
      })
      .finally(() => {
        if (isMounted) setStatsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch current page
  useEffect(() => {
    const cursor = cursorStack[pageIndex];
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await AnalyticsService.getInstance().listJobs({ cursor, limit: PAGE_SIZE });
        if (!cancelled) {
          setRows(result.data.map(mapToRow));
          setNextCursor(result.meta.next_cursor);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
          setRows([]);
          setNextCursor(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [cursorStack, pageIndex]);

  const goToNextPage = useCallback(() => {
    if (!nextCursor) return;
    setCursorStack((prev) => {
      const updated = [...prev];
      updated[pageIndex + 1] = nextCursor;
      return updated;
    });
    setPageIndex((p) => p + 1);
  }, [nextCursor, pageIndex]);

  const goToPrevPage = useCallback(() => {
    setPageIndex((p) => Math.max(0, p - 1));
  }, []);

  return {
    rows,
    stats,
    loading,
    statsLoading,
    error,
    hasNextPage: Boolean(nextCursor),
    hasPrevPage: pageIndex > 0,
    page: pageIndex + 1,
    goToNextPage,
    goToPrevPage,
  };
}
