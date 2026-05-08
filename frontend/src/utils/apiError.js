const FIELD_MAP = {
    // Historial Clínico (UX crítica)
    diagnosis: "Diagnóstico",
    treatment: "Tratamiento",
    notes: "Notas",
    consultation_type: "Tipo de consulta",
    weight: "Peso",
    temperature: "Temperatura",
    heart_rate: "Frecuencia cardíaca",
    respiratory_rate: "Frecuencia respiratoria",
    
    // Recetas
    dose: "Dosis",
    duration: "Duración",
    quantity: "Cantidad",
    instructions: "Instrucciones",
    product: "Producto",
    prescription: "Receta",
    
    // Citas
    appointment_date: "Fecha de cita",
    start_time: "Hora de inicio",
    end_time: "Hora de fin",
    veterinarian: "Veterinario",
    
    // Facturación
    invoice: "Factura",
    service: "Servicio",
    payment_method: "Método de pago",
    discount: "Descuento",
    
    // Inventario
    presentation: "Presentación",
    stock: "Stock",
    min_stock: "Stock mínimo",
    sale_price: "Precio de venta",
    unit_price: "Precio unitario",
    
    // Pacientes
    pet: "Mascota",
    owner: "Propietario",
    species: "Especie",
    breed: "Raza",
    date_of_birth: "Fecha de nacimiento",
    phone: "Teléfono",
    email: "Email",
    
    // Genéricos
    name: "Nombre",
    password: "Contraseña",
    reason: "Motivo",
    medical_record: "Historial clínico",
};

/**
 * Extrae el primer mensaje legible de un error de respuesta DRF.
 * Orden de prioridad:
 *   1. 429 → message / detail / fallback fijo
 *   2. detail → auth / permisos
 *   3. error → errores manuales en views
 *   4. errors[] → array plano de mensajes
 *   5. errors{} → errores de serializer por campo (con traducción de keys)
 *   6. message → formato estándar {code, message}
 *   7. Array → errores no-field
 *   8. Object.values → último recurso
 */
export function apiError(err, fallback = "Error inesperado") {
    const data = err?.response?.data;
    if (!data) return fallback;

    // 429 — resuelve aquí, nunca cae en Object.values
    if (err?.response?.status === 429) {
        return data.message || data.detail || "Demasiadas solicitudes. Intenta en unos minutos.";
    }

    if (typeof data === "string") return data;
    if (data.detail) return String(data.detail);
    if (data.error) return String(data.error);

    // validation_error: array plano
    if (Array.isArray(data.errors)) {
        return String(data.errors[0]) || fallback;
    }

    // validation_error: errores por campo → solo el primer mensaje legible
    if (data.errors && typeof data.errors === "object" && !Array.isArray(data.errors)) {
        const entries = Object.entries(data.errors);
        if (entries.length) {
            const [field, msgs] = entries[0];
            const msg = Array.isArray(msgs) ? msgs[0] : msgs;
            // Fallback inteligente: FIELD_MAP o nombre humanizado
            const label = FIELD_MAP[field] || String(field).replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            return `${label}: ${msg}`;
        }
    }

    if (data.message) return String(data.message);
    if (Array.isArray(data)) return String(data[0]) ?? fallback;
    const first = Object.values(data).flat()[0];
    return first ? String(first) : fallback;
}
