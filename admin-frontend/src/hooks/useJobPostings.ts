import { useCallback, useEffect, useState } from "react";
import AnalyticsService from "src/analytics/AnalyticsService";
import type { JobPostingRow, JobPostingStats } from "src/types";

const PAGE_SIZE = 20;

let _counter = 0;
const nextId = () => String(++_counter);

const normalizeOptionalText = (value?: string): string | null => {
  if (value == null) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

function mapToRow(doc: {
  title?: string;
  category?: string;
  location?: string;
  application_url?: string;
  source_platform?: string;
  skills?: string[];
  posted_date?: string;
}): JobPostingRow {
  return {
    id: nextId(),
    jobTitle: normalizeOptionalText(doc.title),
    sector: normalizeOptionalText(doc.category),
    location: normalizeOptionalText(doc.location),
    zqfLevel: "",
    platform: normalizeOptionalText(doc.source_platform),
    skills: Array.isArray(doc.skills) ? doc.skills : [],
    candidatePool: 0,
    jobUrl: doc.application_url ?? "",
    postedDate: doc.posted_date,
  };
}

export interface UseJobPostingsResult {
  rows: JobPostingRow[];
  stats: JobPostingStats;
  loading: boolean;
  statsLoading: boolean;
  error: Error | null;
  /** 1-based index of the current page (for the range label). */
  pageIndex: number;
  totalItems: number;
  hasPrev: boolean;
  hasNext: boolean;
  goNext: () => void;
  goPrev: () => void;
}

export interface JobPostingQueryFilters {
  searchQuery: string;
  sectorQuery?: string;
  locationQuery?: string;
  skillsQuery?: string;
}

export function useJobPostings({
  searchQuery,
  sectorQuery = "",
  locationQuery = "",
  skillsQuery = "",
}: JobPostingQueryFilters): UseJobPostingsResult {
  // Server-side cursor pagination: `cursorStack` holds the cursor used to fetch each visited
  // page (first page = undefined). "previous" pops; "next" pushes the response's next_cursor.
  const [cursorStack, setCursorStack] = useState<(string | undefined)[]>([undefined]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [rows, setRows] = useState<JobPostingRow[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [stats, setStats] = useState<JobPostingStats>({ jobsSourced: 0, sectorsCovered: 0, sourcePlatformsCount: 0 });
  const [statsLoading, setStatsLoading] = useState(true);
  const normalizedSearchQuery = searchQuery.trim();
  const normalizedSectorQuery = sectorQuery.trim();
  const normalizedLocationQuery = locationQuery.trim();
  const normalizedSkillsQuery = skillsQuery.trim();

  // Reset to the first page whenever the filters change.
  useEffect(() => {
    setCursorStack([undefined]);
    setNextCursor(null);
  }, [normalizedSearchQuery, normalizedSectorQuery, normalizedLocationQuery, normalizedSkillsQuery]);

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

  const currentCursor = cursorStack[cursorStack.length - 1];

  // Fetch current page
  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await AnalyticsService.getInstance().listJobs({
          search: normalizedSearchQuery || undefined,
          category: normalizedSectorQuery || undefined,
          location: normalizedLocationQuery || undefined,
          skills: normalizedSkillsQuery || undefined,
          cursor: currentCursor,
          limit: PAGE_SIZE,
          include: "count",
        });
        if (!cancelled) {
          setRows(result.data.map(mapToRow));
          setNextCursor(result.meta.next_cursor);
          if (typeof result.meta.total === "number") {
            setTotalItems(result.meta.total);
          }
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
  }, [currentCursor, normalizedSearchQuery, normalizedSectorQuery, normalizedLocationQuery, normalizedSkillsQuery]);

  const goNext = useCallback(() => {
    if (nextCursor == null) return;
    setCursorStack((prev) => [...prev, nextCursor]);
  }, [nextCursor]);

  const goPrev = useCallback(() => {
    setCursorStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }, []);

  return {
    rows,
    stats,
    loading,
    statsLoading,
    error,
    pageIndex: cursorStack.length,
    totalItems,
    hasPrev: cursorStack.length > 1,
    hasNext: nextCursor != null,
    goNext,
    goPrev,
  };
}
