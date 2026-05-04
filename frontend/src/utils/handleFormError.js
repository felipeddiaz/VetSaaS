import mapFieldErrors from "./mapFieldErrors";
import { apiError } from "./apiError";
import { toast } from "sonner";

/**
 * handleFormError — Handler centralizado para errores en formularios
 *
 * Comportamiento:
 *   - Si hay errores de campo → setErrors con merge + limpieza
 *   - Si no hay errores de campo → toast con mensaje global
 *
 * Parámetros:
 *   err: axios error
 *   setErrors: React setState para estado de errores del formulario
 *   opts.merge: true (default) — merge con errores previos; false — reemplaza todo
 *
 * Uso:
 *   try {
 *     await apiCall(payload);
 *   } catch (err) {
 *     handleFormError(err, setFormErrors);
 *   }
 */
export default function handleFormError(err, setErrors, opts = { merge: true }) {
  const data = err?.response?.data;
  const fieldErrors = mapFieldErrors(data || {});

  if (Object.keys(fieldErrors).length > 0) {
    // Errores por campo → mostrar inline
    if (opts.merge) {
      setErrors(prev => {
        const clean = { ...(prev || {}) };
        // Eliminar claves que van a ser reemplazadas para evitar errores "pegados"
        Object.keys(fieldErrors).forEach(k => delete clean[k]);
        return { ...clean, ...fieldErrors };
      });
    } else {
      setErrors(fieldErrors);
    }
    return;
  }

  // Sin errores de campo → toast global (permisos, network, etc.)
  toast.error(apiError(err));
}
