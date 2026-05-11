import { useState, useEffect, useCallback, useMemo } from "react";
import { getStatusBreakdown } from "../api/statusBreakdown";

const STATUS_LABELS = {
  scheduled: "Programadas",
  confirmed: "Confirmadas",
  in_progress: "En consulta",
  done: "Completadas",
  canceled: "Canceladas",
  no_show: "No se presentó",
};

const PIE_COLORS = {
  scheduled:   "var(--c-info-text)",
  confirmed:   "var(--c-purple-text)",
  in_progress: "var(--c-accent)",
  done:        "var(--c-success-text)",
  canceled:    "var(--c-danger-text)",
  no_show:     "var(--c-text-3)",
};

export function useAppointmentsByStatus(dateRange) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!dateRange) return;
    setLoading(true);
    setError(null);
    try {
      const raw = await getStatusBreakdown({ from: dateRange.from, to: dateRange.to });
      setData(raw);
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError("No se pudieron cargar las citas del periodo.");
      }
    } finally {
      setLoading(false);
    }
  }, [dateRange?.from, dateRange?.to]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const pieData = useMemo(() => {
    if (!data) return [];
    return data.status_order
      .filter((s) => data.totals[s] > 0)
      .map((s) => ({
        name: STATUS_LABELS[s] || s,
        key: s,
        value: data.totals[s],
        fill: PIE_COLORS[s] || "var(--c-text-3)",
      }));
  }, [data]);

  const byStatus = data?.by_status || {};
  const totals = data?.totals || {};
  const statusOrder = data?.status_order || [];
  const grandTotal = useMemo(() => Object.values(totals).reduce((a, b) => a + b, 0), [totals]);

  return {
    byStatus,
    totals,
    statusOrder,
    pieData,
    grandTotal,
    loading,
    error,
    refetch: fetchData,
  };
}
