/**
 * mapFieldErrors — Normaliza respuestas DRF a claves planas (Opción A determinista)
 *
 * Comportamiento:
 *   - Top-level: sale_price: ["X"] → sale_price: "X"
 *   - Nested: presentation_input: { sale_price: ["Y"] } → presentation_input.sale_price: "Y"
 *   - Colisión: ambas claves se guardan (nunca se sobrescribe):
 *     sale_price: ["X"], presentation_input: { sale_price: ["Y"] }
 *     → { sale_price: "X", "presentation_input.sale_price": "Y" }
 *
 * Razonamiento:
 *   1. Intenta guardar en root primero (sale_price).
 *   2. Si ya existe en root, también guarda la versión nested (presentation_input.sale_price).
 *   3. Nunca sobrescribe; determinista para ambos casos.
 */
export default function mapFieldErrors(data = {}) {
  const result = {};

  if (!data || typeof data !== "object") {
    return result;
  }

  // Procesa top-level y nested entries
  Object.entries(data).forEach(([key, value]) => {
    if (Array.isArray(value) || typeof value !== "object") {
      // Top-level field: sale_price: ["X"] → sale_price: "X"
      const plainVal = Array.isArray(value) ? value[0] : String(value);
      result[key] = plainVal;
      return;
    }

    // Nested object: presentation_input: { sale_price: ["Y"], stock: ["Z"] }
    Object.entries(value).forEach(([innerKey, innerVal]) => {
      const plainVal = Array.isArray(innerVal) ? innerVal[0] : String(innerVal);

      // Intenta escribir en root primero
      if (!result.hasOwnProperty(innerKey)) {
        // No existe en root → guarda aquí
        result[innerKey] = plainVal;
      } else {
        // Colisión: ya existe en root, guarda además la versión nested
        // Nunca sobrescribe la raíz
      }

      // Siempre guarda la versión nested (presentation_input.sale_price)
      const nestedKey = `${key}.${innerKey}`;
      if (!result.hasOwnProperty(nestedKey)) {
        result[nestedKey] = plainVal;
      }
    });
  });

  return result;
}
