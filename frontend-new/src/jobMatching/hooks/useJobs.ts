import { useCallback, useContext, useEffect, useState } from "react";
import { ReconnectVersionContext } from "src/app/isOnlineProvider/IsOnlineProvider";
import JobService from "src/jobMatching/services/JobService";
import type { JobApiDocument, JobFilters, JobRow } from "src/jobMatching/types";

export const PAGE_SIZE = 20;

let _rowCounter = 0;
const nextId = () => String(++_rowCounter);

function mapDocToRow(doc: JobApiDocument): JobRow {
  return {
    id: nextId(),
    jobTitle: doc.title ?? "",
    company: doc.employer ?? "",
    category: doc.category ?? "",
    employmentType: doc.employment_type ?? "",
    location: doc.location ?? "",
    posted: doc.posted_date ?? "",
    jobUrl: doc.application_url ?? undefined,
    skills: Array.isArray(doc.skills) ? doc.skills : undefined,
  };
}

export interface UseJobsResult {
  jobs: JobRow[];
  loading: boolean;
  error: unknown;
  /** 1-based index of the current page (for the range label). */
  pageIndex: number;
  totalItems: number;
  hasPrev: boolean;
  hasNext: boolean;
  goNext: () => void;
  goPrev: () => void;
  reload: () => void;
}

export function useJobs(filters: JobFilters): UseJobsResult {
  const reconnectVersion = useContext(ReconnectVersionContext);
  // Server-side cursor pagination: `cursorStack` holds the cursor used to fetch each
  // visited page (first page = undefined). The current page is the last entry; "previous"
  // pops the stack and "next" pushes the response's next_cursor.
  const [cursorStack, setCursorStack] = useState<(string | undefined)[]>([undefined]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Reset to the first page whenever the query context changes.
  useEffect(() => {
    setCursorStack([undefined]);
    setNextCursor(null);
  }, [filters.search, filters.category, filters.employmentType, filters.location]);

  const currentCursor = cursorStack[cursorStack.length - 1];

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const searchValue = filters.search.trim();
        const result = await JobService.getInstance().listJobs({
          search: searchValue.length > 0 ? searchValue : undefined,
          category: filters.category !== "all" ? filters.category : undefined,
          employment_type: filters.employmentType !== "all" ? filters.employmentType : undefined,
          location: filters.location !== "all" ? filters.location : undefined,
          cursor: currentCursor,
          include: "count",
          limit: PAGE_SIZE,
        });
        if (!cancelled) {
          setJobs(result.data.map(mapDocToRow));
          setNextCursor(result.meta.next_cursor);
          if (typeof result.meta.total === "number") {
            setTotalItems(result.meta.total);
          }
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e);
          setJobs([]);
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
  }, [currentCursor, filters.search, filters.category, filters.employmentType, filters.location, reconnectVersion]);

  const goNext = useCallback(() => {
    if (nextCursor == null) return;
    setCursorStack((prev) => [...prev, nextCursor]);
  }, [nextCursor]);

  const goPrev = useCallback(() => {
    setCursorStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }, []);

  const reload = useCallback(() => {
    setCursorStack([undefined]);
    setNextCursor(null);
  }, []);

  return {
    jobs,
    loading,
    error,
    pageIndex: cursorStack.length,
    totalItems,
    hasPrev: cursorStack.length > 1,
    hasNext: nextCursor != null,
    goNext,
    goPrev,
    reload,
  };
}
