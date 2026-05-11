import { useState, useEffect, useCallback } from "react";
import { getOperationsSeries } from "../api/analytics";
import * as Sentry from "@sentry/react";

const DECIMAL_KEYS = ["revenuePaid", "revenueAccrual"];
const METRIC_KEY_MAP = {
  appointments_total: "appointmentsTotal",
  appointments_done: "appointmentsDone",
  appointments_no_show: "appointmentsNoShow",
  medical_records_closed: "medicalRecordsClosed",
  revenue_paid: "revenuePaid",
  revenue_accrual: "revenueAccrual",
  invoices_paid_count: "invoicesPaidCount",
};

function normalizeMetrics(raw) {
  if (!raw) return null;
  const out = {};
  for (const [k, v] of Object.entries(raw)) {
    const key = METRIC_KEY_MAP[k] || k;
    if (DECIMAL_KEYS.includes(key)) {
      out[key] = Number(v ?? 0);
    } else {
      out[key] = Number(v ?? 0);
    }
  }
  return out;
}

function enrichDatapoint(raw, isToday = false) {
  const lifecycleState = raw.lifecycle_state ?? null;
  const source = raw.source ?? "snapshot";
  const isMissing = lifecycleState === "missing" || raw.lifecycleState === "missing";
  const isLive = source === "live";

  return {
    bucketDate: raw.bucket_date || raw.bucketDate,
    source,
    lifecycleState,
    isToday,
    isMissing,
    isLive,
    isFrozen: lifecycleState === "frozen",
    isProvisional: lifecycleState === "provisional",
    metrics: isMissing ? null : normalizeMetrics(raw.metrics),
    metricsSchemaVersion: raw.metrics_schema_version ?? raw.metricsSchemaVersion ?? null,
  };
}

export function useDashboardSeries(rangeDays = 30, includeToday = true) {
  const [allPoints, setAllPoints] = useState([]);
  const [range, setRange] = useState(null);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastSnapshotDate, setLastSnapshotDate] = useState(null);
  const [hasHistory, setHasHistory] = useState(false);
  const [hasActivity, setHasActivity] = useState(false);
  const [hasCorrupt, setHasCorrupt] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - (rangeDays - 1));
      to.setHours(23, 59, 59, 999);

      const data = await getOperationsSeries({ from, to, includeToday });

      const enrichedSeries = (data.series || []).map((dp) => {
        const enriched = enrichDatapoint(dp, false);

        if (dp.lifecycle_state === "corrupt" || dp.lifecycleState === "corrupt") {
          Sentry.captureException(
            new Error(`Corrupt datapoint reached frontend: ${enriched.bucketDate}`),
            { extra: { bucketDate: enriched.bucketDate, lifecycleState: dp.lifecycle_state } }
          );
          return null;
        }
        return enriched;
      });

      const corruptCount = enrichedSeries.filter((p) => p === null).length;
      const filtered = enrichedSeries.filter(Boolean);

      const todayPoint = data.today ? enrichDatapoint(data.today, true) : null;
      const points = todayPoint ? [...filtered, todayPoint] : filtered;

      const lastSnap = filtered
        .filter((p) => !p.isMissing && !p.isLive)
        .pop();
      setLastSnapshotDate(lastSnap?.bucketDate ?? null);

      setRange(data.range ?? null);
      setNotes(data.notes ?? []);
      setAllPoints(points);

      const hist = points.some((p) => !p.isToday && !p.isMissing);
      const act = points.some(
        (p) =>
          p.metrics !== null &&
          (p.metrics.appointmentsTotal > 0 ||
            p.metrics.appointmentsDone > 0 ||
            p.metrics.medicalRecordsClosed > 0)
      );
      setHasHistory(hist);
      setHasActivity(act);
      setHasCorrupt(corruptCount > 0);
    } catch (err) {
      if (err?.name !== "AbortError") {
        const msg =
          err?.response?.status === 403
            ? "No tienes permiso para ver estos datos."
            : "No se pudo cargar la información del dashboard.";
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [rangeDays, includeToday]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const onFocus = () => fetchData();
    window.addEventListener("focus", onFocus);
    window.addEventListener("dashboard:refresh", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("dashboard:refresh", onFocus);
    };
  }, [fetchData]);

  return {
    allPoints,
    range,
    notes,
    loading,
    error,
    lastSnapshotDate,
    hasHistory,
    hasActivity,
    hasCorrupt,
    refetch: fetchData,
  };
}
