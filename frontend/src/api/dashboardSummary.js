import api from "./client";

export const getDashboardSummary = () =>
    api.get("v1/dashboard/summary/").then((r) => r.data);
