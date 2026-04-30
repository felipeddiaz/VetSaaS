import { useEffect, useMemo, useState } from "react";
import { apiError } from "../../utils/apiError";
import { getPets } from "../../api/pets";
import { getPresentations } from "../../api/inventory";
import { Icon } from "../icons";
import SearchSelect from "../SearchSelect";
import { toast } from "sonner";

const EMPTY_ITEM = { product: "", _productLabel: "", dose: "", duration: "", quantity: "", instructions: "" };

const buildInitialForm = (initialValue = {}) => ({
    medical_record: initialValue.medical_record || "",
    pet: initialValue.pet || "",
    notes: initialValue.notes || "",
    items: initialValue.items?.length
        ? initialValue.items.map(item => ({
            product: item.product || "",
            dose: item.dose || "",
            duration: item.duration || "",
            quantity: item.quantity || "",
            instructions: item.instructions || "",
        }))
        : [{ ...EMPTY_ITEM }],
});

const PrescriptionForm = ({
    title,
    initialValue,
    pets,
    products,
    medicalRecordsForPet,
    lockedPet = false,
    lockedMedicalRecord = false,
    submitLabel,
    onPetChange,
    onSubmit,
    onCancel,
}) => {
    const [form, setForm] = useState(() => buildInitialForm(initialValue));
    const [itemErrors, setItemErrors] = useState(new Set());
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        setForm(buildInitialForm(initialValue));
        setItemErrors(new Set());
        setSubmitting(false);
    }, [initialValue]);

    useEffect(() => {
        if (form.pet && onPetChange) {
            onPetChange(form.pet);
        }
    }, [form.pet, onPetChange]);

    const availableMedicalRecords = useMemo(
        () => medicalRecordsForPet.filter(r => !r.prescription_id || String(r.id) === String(form.medical_record)),
        [medicalRecordsForPet, form.medical_record],
    );

    const addItem = () => setForm(prev => ({ ...prev, items: [...prev.items, { ...EMPTY_ITEM }] }));

    const removeItem = (index) => {
        if (form.items.length === 1) return;
        setForm(prev => ({ ...prev, items: prev.items.filter((_, i) => i !== index) }));
    };

    const updateItem = (index, field, value) => {
        setForm(prev => ({
            ...prev,
            items: prev.items.map((item, i) => i === index ? { ...item, [field]: value } : item),
        }));
        if (itemErrors.has(index)) {
            setItemErrors(prev => { const next = new Set(prev); next.delete(index); return next; });
        }
    };

    const handlePetChange = (value) => {
        setForm(prev => ({ ...prev, pet: value, medical_record: lockedMedicalRecord ? prev.medical_record : "" }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setItemErrors(new Set());

        if (!form.pet) { toast.error("Selecciona una mascota"); return; }
        if (!form.medical_record) { toast.error("Selecciona la consulta médica asociada"); return; }

        const hasProduct = (item) => item.product !== "" && item.product !== null && item.product !== undefined;

        const incompleteIndices = form.items.reduce((acc, item, i) => {
            if (hasProduct(item) && (!item.dose.trim() || !Number(item.quantity))) acc.push(i);
            return acc;
        }, []);
        if (incompleteIndices.length > 0) {
            setItemErrors(new Set(incompleteIndices));
            toast.error(
                incompleteIndices.length === 1
                    ? `El medicamento ${incompleteIndices[0] + 1} tiene dosis o cantidad incompleta`
                    : `Los medicamentos ${incompleteIndices.map(i => i + 1).join(", ")} tienen dosis o cantidad incompleta`
            );
            return;
        }

        const validItems = form.items.filter(hasProduct);
        if (validItems.length === 0) {
            toast.error("Agrega al menos un medicamento con producto, dosis y cantidad");
            return;
        }

        const payload = {
            pet: form.pet,
            medical_record: form.medical_record,
            notes: form.notes,
            items: validItems.map(i => ({
                product: i.product,
                dose: i.dose,
                duration: i.duration,
                quantity: i.quantity,
                instructions: i.instructions,
            })),
        };

        try {
            setSubmitting(true);
            await onSubmit(payload);
        } catch (err) {
            toast.error(apiError(err, "Error al guardar la receta"));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="modal-overlay">
            <div className="modal modal-md">
                <div className="modal-header">
                    <h3>{title}</h3>
                    <button className="modal-close" onClick={onCancel}><Icon.X s={16} /></button>
                </div>
                <div className="modal-body">
                    <form onSubmit={handleSubmit}>
                        <div className="form-group">
                            <label className="form-label" htmlFor="prescription-pet">MASCOTA *</label>
                            {lockedPet ? (
                                <p style={{ margin: 0, fontWeight: 500, fontSize: "14px" }}>
                                    {pets.find(p => String(p.id) === String(form.pet))?.name ?? form.pet}
                                </p>
                            ) : (
                                <SearchSelect
                                    id="prescription-pet"
                                    name="prescription-pet"
                                    value={form.pet ? { id: form.pet, label: pets.find(p => String(p.id) === String(form.pet))?.name ?? "" } : null}
                                    onChange={item => handlePetChange(item?.id ?? "")}
                                    onSearch={q => getPets({ search: q }).then(ps => ps.map(p => ({ id: p.id, label: p.name })))}
                                    placeholder="Buscar mascota..."
                                    disabled={submitting}
                                />
                            )}
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="prescription-medical-record">CONSULTA MÉDICA *</label>
                            {!form.pet ? (
                                <p style={{ margin: 0, color: "var(--c-text-3)", fontSize: "13px" }}>Selecciona una mascota primero</p>
                            ) : availableMedicalRecords.length === 0 ? (
                                <p style={{ margin: 0, color: "var(--c-text-3)", fontSize: "13px" }}>Esta mascota no tiene consultas disponibles.</p>
                            ) : (
                                <select
                                    id="prescription-medical-record"
                                    name="prescription-medical-record"
                                    className="select-input"
                                    value={form.medical_record}
                                    onChange={e => setForm(prev => ({ ...prev, medical_record: e.target.value }))}
                                    disabled={lockedMedicalRecord || submitting}
                                >
                                    <option value="">Seleccionar consulta</option>
                                    {availableMedicalRecords.map(r => {
                                        const date = new Date(r.created_at).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
                                        const diag = (r.diagnosis || "").substring(0, 50);
                                        return <option key={r.id} value={r.id}>{date} - {diag}</option>;
                                    })}
                                </select>
                            )}
                        </div>

                        <div className="form-group">
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                                <label className="form-label" style={{ marginBottom: 0 }}>MEDICAMENTOS *</label>
                                <button type="button" className="btn btn-primary btn-sm" onClick={addItem} disabled={submitting}>
                                    + Agregar
                                </button>
                            </div>

                            {form.items.map((item, index) => {
                            const hasItemError = itemErrors.has(index);
                            return (
                                <div key={index} className="card" style={{ padding: "14px", marginBottom: "10px", background: hasItemError ? "rgba(239,68,68,.04)" : "var(--c-subtle)", borderColor: hasItemError ? "#ef4444" : undefined }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                                        <span style={{ fontWeight: "600", fontSize: "12px", color: "var(--c-text-2)" }}>Medicamento {index + 1}</span>
                                        {form.items.length > 1 && (
                                            <button type="button" className="btn btn-danger btn-xs" onClick={() => removeItem(index)} disabled={submitting}>
                                                <Icon.X s={11} />
                                            </button>
                                        )}
                                    </div>

                                    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "8px", marginBottom: "8px" }}>
                                        <div>
                                            <label style={{ fontSize: "12px", color: "var(--c-text-2)", display: "block", marginBottom: "4px" }} htmlFor={`prescription-item-product-${index}`}>Producto *</label>
                                            <SearchSelect
                                                id={`prescription-item-product-${index}`}
                                                name={`prescription-item-product-${index}`}
                                                value={item.product ? { id: item.product, label: item._productLabel || String(item.product) } : null}
                                                onChange={sel => {
                                                    updateItem(index, "product", sel ? sel.id : "");
                                                    updateItem(index, "_productLabel", sel ? sel.label : "");
                                                }}
                                                onSearch={async (q) => {
                                                    const data = await getPresentations({ product__category: "medication", "stock__gt": 0, search: q });
                                                    return data.slice(0, 10).map(p => ({
                                                        id: p.product,
                                                        label: `${p.product_name} — ${p.base_unit_display || p.base_unit} (stock: ${p.stock})`,
                                                    }));
                                                }}
                                                placeholder="Buscar medicamento..."
                                                disabled={submitting}
                                            />
                                        </div>
                                        <div>
                                            <label style={{ fontSize: "12px", color: "var(--c-text-2)", display: "block", marginBottom: "4px" }} htmlFor={`prescription-item-quantity-${index}`}>Cantidad *</label>
                                            <input
                                                id={`prescription-item-quantity-${index}`}
                                                name={`prescription-item-quantity-${index}`}
                                                type="number"
                                                step="0.01"
                                                min="0.01"
                                                className="input"
                                                value={item.quantity}
                                                onChange={e => updateItem(index, "quantity", e.target.value)}
                                                placeholder="0"
                                                disabled={submitting}
                                                style={hasItemError && !Number(item.quantity) ? { borderColor: "#ef4444" } : {}}
                                            />
                                        </div>
                                    </div>

                                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "8px" }}>
                                        <div>
                                            <label style={{ fontSize: "12px", color: "var(--c-text-2)", display: "block", marginBottom: "4px" }} htmlFor={`prescription-item-dose-${index}`}>Dosis *</label>
                                            <input
                                                id={`prescription-item-dose-${index}`}
                                                name={`prescription-item-dose-${index}`}
                                                type="text"
                                                className="input"
                                                value={item.dose}
                                                onChange={e => updateItem(index, "dose", e.target.value)}
                                                placeholder="Ej: 1 comprimido cada 12h"
                                                disabled={submitting}
                                                style={hasItemError && !item.dose.trim() ? { borderColor: "#ef4444" } : {}}
                                            />
                                        </div>
                                        <div>
                                            <label style={{ fontSize: "12px", color: "var(--c-text-2)", display: "block", marginBottom: "4px" }} htmlFor={`prescription-item-duration-${index}`}>Duración</label>
                                            <input
                                                id={`prescription-item-duration-${index}`}
                                                name={`prescription-item-duration-${index}`}
                                                type="text"
                                                className="input"
                                                value={item.duration}
                                                onChange={e => updateItem(index, "duration", e.target.value)}
                                                placeholder="Ej: 7 días"
                                                disabled={submitting}
                                            />
                                        </div>
                                    </div>

                                    <div>
                                        <label style={{ fontSize: "12px", color: "var(--c-text-2)", display: "block", marginBottom: "4px" }} htmlFor={`prescription-item-instructions-${index}`}>Instrucciones adicionales</label>
                                        <input
                                            id={`prescription-item-instructions-${index}`}
                                            name={`prescription-item-instructions-${index}`}
                                            type="text"
                                            className="input"
                                            value={item.instructions}
                                            onChange={e => updateItem(index, "instructions", e.target.value)}
                                            placeholder="Ej: Administrar con comida"
                                            disabled={submitting}
                                        />
                                    </div>
                                </div>
                            ); })}
                        </div>

                        <div className="form-group">
                            <label className="form-label" htmlFor="prescription-notes">NOTAS</label>
                            <textarea
                                id="prescription-notes"
                                name="prescription-notes"
                                className="textarea-input"
                                value={form.notes}
                                onChange={e => setForm(prev => ({ ...prev, notes: e.target.value }))}
                                placeholder="Observaciones adicionales..."
                                style={{ minHeight: "60px" }}
                                disabled={submitting}
                            />
                        </div>

                        <div className="modal-footer" style={{ padding: 0, border: 0, marginTop: "20px" }}>
                            <button type="submit" className="btn btn-primary btn-md" style={{ flex: 1 }} disabled={submitting}>
                                {submitting ? "Guardando..." : submitLabel}
                            </button>
                            <button type="button" className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={onCancel} disabled={submitting}>
                                Cancelar
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};

export default PrescriptionForm;
