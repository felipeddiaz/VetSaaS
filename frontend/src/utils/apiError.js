/**
 * Extrae el primer mensaje legible de un error de respuesta DRF.
 * DRF puede devolver:
 *   {"detail": "..."}               → auth / permisos
 *   {"error": "..."}                → errores manuales en views
 *   {"field": ["msg", ...], ...}    → errores de serializer por campo
 *   ["msg1", "msg2"]                → errores no-field
 */
export function apiError(err, fallback = "Error inesperado") {
    const data = err?.response?.data;
    if (!data) return fallback;
    if (typeof data === "string") return data;
    if (data.detail) return String(data.detail);
    if (data.error)  return String(data.error);
    if (Array.isArray(data)) return String(data[0]) ?? fallback;
    const first = Object.values(data).flat()[0];
    return first ? String(first) : fallback;
}
