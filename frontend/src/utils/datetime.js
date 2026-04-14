const toUtcIso = (value) => {
    if (!value) return null;
    if (typeof value === "string" && (value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value))) {
        return value;
    }
    if (typeof value === "string") {
        return `${value}Z`;
    }
    return null;
};

export const formatDateTime = (isoUtc, tz = "UTC", locale = "es-ES") => {
    const normalized = toUtcIso(isoUtc);
    if (!normalized) return "";
    const dt = new Date(normalized);
    if (Number.isNaN(dt.getTime())) return "";

    return new Intl.DateTimeFormat(locale, {
        timeZone: tz,
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(dt);
};

export const formatDate = (isoUtc, tz = "UTC", locale = "es-ES") => {
    const normalized = toUtcIso(isoUtc);
    if (!normalized) return "";
    const dt = new Date(normalized);
    if (Number.isNaN(dt.getTime())) return "";

    return new Intl.DateTimeFormat(locale, {
        timeZone: tz,
        year: "numeric",
        month: "long",
        day: "numeric",
    }).format(dt);
};
