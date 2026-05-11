import { useState, useEffect, useCallback } from "react";
import { getFinancialSeries } from "../api/analytics";

function parseFinMetrics(raw) {
  if (!raw) return null;
  return {
    revenuePaid: Number(raw.revenue_paid ?? 0),
    revenueAccrual: Number(raw.revenue_accrual ?? 0),
    invoicesPaidCount: Number(raw.invoices_paid_count ?? 0),
  };
}

export function useFinancialSeries(rangeDays = 30, includeToday = true) {
  const [series, setSeries] = useState([]);
  const [today, setToday] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - (rangeDays - 1));

      const data = await getFinancialSeries({ from, to, includeToday });
      setSeries(
        (data.series || []).map((dp) => ({
          bucketDate: dp.bucket_date,
          lifecycleState: dp.lifecycle_state ?? null,
          source: dp.source,
          metrics: parseFinMetrics(dp.metrics),
        }))
      );
      setToday(
        data.today
          ? {
              bucketDate: data.today.bucket_date,
              lifecycleState: null,
              source: "live",
              metrics: parseFinMetrics(data.today.metrics),
            }
          : null
      );
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError(err?.response?.status === 403 ? "Sin permiso" : "Error al cargar datos financieros.");
      }
    } finally {
      setLoading(false);
    }
  }, [rangeDays, includeToday]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return { series, today, loading, error, refetch: fetchData };
}
