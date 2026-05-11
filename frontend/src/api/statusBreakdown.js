import api from "./client";

const fmt = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

export const getStatusBreakdown = ({ from, to }) => {
  const p = new URLSearchParams();
  if (from instanceof Date) p.set("from", fmt(from));
  else if (from) p.set("from", from);
  if (to instanceof Date) p.set("to", fmt(to));
  else if (to) p.set("to", to);
  return api.get(`appointments/status-breakdown/?${p.toString()}`).then((r) => r.data);
};
