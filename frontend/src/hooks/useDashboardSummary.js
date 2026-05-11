import { useState, useEffect, useCallback, useRef } from "react";
import { getDashboardSummary } from "../api/dashboardSummary";

const POLL_INTERVAL = 30_000;

export function useDashboardSummary() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);
  const mountedRef = useRef(true);

  const fetch = useCallback(async () => {
    try {
      const result = await getDashboardSummary();
      if (mountedRef.current) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetch();

    timerRef.current = setInterval(fetch, POLL_INTERVAL);

    const onRefresh = () => fetch();
    window.addEventListener("dashboard:refresh", onRefresh);

    return () => {
      mountedRef.current = false;
      clearInterval(timerRef.current);
      window.removeEventListener("dashboard:refresh", onRefresh);
    };
  }, [fetch]);

  const refetch = useCallback(() => {
    setLoading(true);
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch };
}
