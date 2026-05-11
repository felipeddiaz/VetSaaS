import { useState, useEffect, useCallback } from "react";
import { getMedicalRecords } from "../api/medicalRecords";

export function useOpenRecords(limit = 5) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMedicalRecords(null, {
        status: "open",
        page_size: String(limit),
      });
      const list = Array.isArray(data) ? data : data?.results || [];
      setRecords(list.slice(0, limit));
    } catch (err) {
      setError("No se pudieron cargar las consultas abiertas.");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    window.addEventListener("dashboard:refresh", fetchData);
    return () => window.removeEventListener("dashboard:refresh", fetchData);
  }, [fetchData]);

  return { records, loading, error, refetch: fetchData };
}
