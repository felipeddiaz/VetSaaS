import api from "./client";

export const getDashboardStats = () =>
    api.get("dashboard/stats/").then(r => r.data);
