import { useCallback, useEffect, useState } from "react";
import JobService from "src/jobMatching/services/JobService";
import type { MatchedJobApiDocument, JobRow } from "src/jobMatching/types";

const PAGE_SIZE = 20;

let _matchedRowCounter = 0;
const nextId = () => String(++_matchedRowCounter);

function mapMatchedDocToRow(doc: MatchedJobApiDocument): JobRow {
  return {
    id: nextId(),
    jobTitle: doc.opportunity_title ?? "",
    company: doc.employer ?? "",
    category: doc.category ?? "",
    employmentType: doc.contract_type ?? "",
    location: doc.location ?? "",
    posted: doc.posted_date ?? "",
    jobUrl: doc.URL ?? undefined,
    matchScore: doc.final_score !== undefined ? Math.round(doc.final_score * 100) : undefined,
  };
}

export interface UseMatchedJobsResult {
  jobs: JobRow[];
  loading: boolean;
  error: string | null;
  hasNextPage: boolean;
  hasPrevPage: boolean;
  page: number;
  goToNextPage: () => void;
  goToPrevPage: () => void;
}

export function useMatchedJobs(active: boolean): UseMatchedJobsResult {
  const [allJobs, setAllJobs] = useState<JobRow[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  useEffect(() => {
    if (!active || fetched) return;
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await JobService.getInstance().getMatchedJobs(PAGE_SIZE);
        if (!cancelled) {
          setAllJobs(data.map(mapMatchedDocToRow));
          setFetched(true);
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load matched jobs");
          setAllJobs([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [active, fetched]);

  const pageJobs = allJobs.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE);
  const hasNextPage = (pageIndex + 1) * PAGE_SIZE < allJobs.length;
  const hasPrevPage = pageIndex > 0;

  const goToNextPage = useCallback(() => {
    if (hasNextPage) setPageIndex((p) => p + 1);
  }, [hasNextPage]);

  const goToPrevPage = useCallback(() => {
    setPageIndex((p) => Math.max(0, p - 1));
  }, []);

  return { jobs: pageJobs, loading, error, hasNextPage, hasPrevPage, page: pageIndex + 1, goToNextPage, goToPrevPage };
}
