import { useEffect, useState } from "react";
import AnalyticsService from "src/analytics/AnalyticsService";
import type { SkillsSupplyStatsResponse } from "src/analytics/AnalyticsService.types";

export interface UseSkillsSupplyStatsResult {
  data: SkillsSupplyStatsResponse | null;
  loading: boolean;
  error: Error | null;
}

export function useSkillsSupplyStats(limit = 10, institution?: string, province?: string, sector?: string): UseSkillsSupplyStatsResult {
  const [data, setData] = useState<SkillsSupplyStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    AnalyticsService.getInstance()
      .getSkillsSupplyStats(limit, institution, province, sector)
      .then((result) => {
        if (!isMounted) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [limit, institution, province, sector]);

  return { data, loading, error };
}
