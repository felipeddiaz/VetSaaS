import api from "./client";

const fmt = (d) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
};

const buildQS = ({ from, to, includeToday = true } = {}) => {
    const p = new URLSearchParams();
    if (from instanceof Date) p.set("from", fmt(from));
    else if (from) p.set("from", from);
    if (to instanceof Date) p.set("to", fmt(to));
    else if (to) p.set("to", to);
    p.set("include_today", includeToday ? "true" : "false");
    return p.toString();
};

export const getOperationsSeries = (opts) =>
    api.get(`v1/dashboard/operations/series/?${buildQS(opts)}`).then(r => r.data);

export const getFinancialSeries = (opts) =>
    api.get(`v1/dashboard/financial/series/?${buildQS(opts)}`).then(r => r.data);

export const getAnalyticsHealth = (orgId) => {
    const q = orgId ? `?org=${orgId}` : "";
    return api.get(`internal/analytics-health/${q}`).then(r => r.data);
};
