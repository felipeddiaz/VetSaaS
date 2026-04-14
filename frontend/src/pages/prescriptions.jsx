import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
    getPrescriptions, getPrescription, createPrescription,
    updatePrescription, deletePrescription, downloadPrescriptionPDF,
} from "../api/prescriptions";
import { getMedicalRecords } from "../api/medicalRecords";
import { getPets } from "../api/pets";
import { getProducts } from "../api/inventory";
import { useAuth } from "../auth/authContext";

const EMPTY_ITEM = { product: "", dose: "", duration: "", quantity: "", instructions: "" };
const EMPTY_FORM = { medical_record: "", pet: "", notes: "", items: [{ ...EMPTY_ITEM }] };

const Prescriptions = () => {
    const { token, user, initializing } = useAuth();
    const [searchParams] = useSearchParams();

    const [prescriptions, setPrescriptions] = useState([]);
    const [pets, setPets] = useState([]);
    const [products, setProducts] = useState([]);
    const [medicalRecordsForPet, setMedicalRecordsForPet] = useState([]);
    const [loading, setLoading] = useState(true);

    const [showModal, setShowModal] = useState(false);
    const [showDetailModal, setShowDetailModal] = useState(false);
    const [editing, setEditing] = useState(null);
    const [viewing, setViewing] = useState(null);
    const [selectedPet, setSelectedPet] = useState("");
    const [lockedFromParams, setLockedFromParams] = useState(false);

    const [form, setForm] = useState(EMPTY_FORM);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");
    const [downloadingId, setDownloadingId] = useState(null);

    useEffect(() => {
        if (token) loadAll();
    }, [token]);

    useEffect(() => {
        loadPrescriptions();
    }, [selectedPet]);

    // Load medical records when selected pet changes in form
    useEffect(() => {
        if (form.pet && token) {
            getMedicalRecords(token, { pet: form.pet })
                .then(data => setMedicalRecordsForPet(data.results || data))
                .catch(() => setMedicalRecordsForPet([]));
        } else {
            setMedicalRecordsForPet([]);
        }
    }, [form.pet, token]);

    // Handle query params ?medical_record=X&pet=Y
    useEffect(() => {
        const mrParam = searchParams.get("medical_record");
        const petParam = searchParams.get("pet");
        if (mrParam && petParam && token) {
            setLockedFromParams(true);
            setForm({ ...EMPTY_FORM, pet: petParam, medical_record: mrParam });
            setShowModal(true);
        }
    }, [searchParams, token]);

    const loadAll = async () => {
        setLoading(true);
        try {
            const [petsData, prodsData] = await Promise.all([
                getPets(token),
                getProducts({ active: "true" }),
            ]);
            setPets(petsData);
            setProducts(prodsData);
            await loadPrescriptions();
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const loadPrescriptions = async () => {
        try {
            const params = {};
            if (selectedPet) params.pet = selectedPet;
            const data = await getPrescriptions(params);
            setPrescriptions(data);
        } catch (err) {
            console.log(err);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");

        if (!form.pet) { setError("Selecciona una mascota"); return; }
        if (!form.medical_record) { setError("Selecciona la consulta médica asociada"); return; }
        const validItems = form.items.filter(i => i.product && i.dose && i.quantity);
        if (validItems.length === 0) { setError("Agrega al menos un medicamento con producto, dosis y cantidad"); return; }

        try {
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

            if (editing) {
                await updatePrescription(editing.id, payload);
                setSuccess("Receta actualizada");
            } else {
                await createPrescription(payload);
                setSuccess("Receta creada");
            }
            loadPrescriptions();
            closeModal();
        } catch (err) {
            setError(err.response?.data?.error || "Error al guardar");
        }
    };

    const handleView = async (prescription) => {
        try {
            const data = await getPrescription(prescription.id);
            setViewing(data);
            setShowDetailModal(true);
        } catch (err) {
            setError("Error al cargar la receta");
        }
    };

    const handleEdit = (prescription) => {
        setEditing(prescription);
        setForm({
            medical_record: prescription.medical_record || "",
            pet: prescription.pet,
            notes: prescription.notes || "",
            items: prescription.items.length > 0
                ? prescription.items.map(i => ({
                    product: i.product,
                    dose: i.dose,
                    duration: i.duration || "",
                    quantity: i.quantity,
                    instructions: i.instructions || "",
                }))
                : [{ ...EMPTY_ITEM }],
        });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        if (!confirm("¿Eliminar esta receta?")) return;
        try {
            await deletePrescription(id);
            setSuccess("Receta eliminada");
            loadPrescriptions();
        } catch (err) {
            setError("Error al eliminar");
        }
    };

    const handleDownloadPDF = async (id) => {
        setDownloadingId(id);
        try {
            const blob = await downloadPrescriptionPDF(id);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `receta_${id}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError("Error al generar el PDF");
        } finally {
            setDownloadingId(null);
        }
    };

    const addItem = () => setForm({ ...form, items: [...form.items, { ...EMPTY_ITEM }] });

    const removeItem = (index) => {
        if (form.items.length === 1) return;
        setForm({ ...form, items: form.items.filter((_, i) => i !== index) });
    };

    const updateItem = (index, field, value) => {
        const items = form.items.map((item, i) => i === index ? { ...item, [field]: value } : item);
        setForm({ ...form, items });
    };

    const closeModal = () => {
        setShowModal(false);
        setEditing(null);
        setForm(EMPTY_FORM);
        setError("");
        setLockedFromParams(false);
        setMedicalRecordsForPet([]);
    };

    const formatDate = (dateString) => {
        return new Date(dateString).toLocaleDateString("es-ES", { year: "numeric", month: "long", day: "numeric" });
    };

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p>Cargando...</p>
            </div>
        );
    }

    const canCreate = user?.role !== "ASSISTANT";

    return (
        <div style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                <h2 style={{ margin: 0 }}>Recetas Médicas</h2>
                {canCreate && (
                    <button
                        onClick={() => { setEditing(null); setForm(EMPTY_FORM); setShowModal(true); }}
                        style={{ padding: "10px 20px", backgroundColor: "#4ecca3", color: "white", border: "none", borderRadius: "5px", cursor: "pointer" }}
                    >
                        + Nueva Receta
                    </button>
                )}
            </div>

            {error && (
                <div style={{ backgroundColor: "#fee2e2", color: "#dc2626", padding: "10px", borderRadius: "5px", marginBottom: "15px" }}>
                    {error} <button onClick={() => setError("")} style={{ float: "right", background: "none", border: "none", cursor: "pointer" }}>✕</button>
                </div>
            )}
            {success && (
                <div style={{ backgroundColor: "#d1fae5", color: "#059669", padding: "10px", borderRadius: "5px", marginBottom: "15px" }}>
                    {success} <button onClick={() => setSuccess("")} style={{ float: "right", background: "none", border: "none", cursor: "pointer" }}>✕</button>
                </div>
            )}

            <div style={{ marginBottom: "20px" }}>
                <select
                    value={selectedPet}
                    onChange={e => setSelectedPet(e.target.value)}
                    style={{ padding: "8px", borderRadius: "5px", border: "1px solid #ddd", minWidth: "200px" }}
                >
                    <option value="">Todas las mascotas</option>
                    {pets.map(pet => <option key={pet.id} value={pet.id}>{pet.name}</option>)}
                </select>
            </div>

            {prescriptions.length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px", color: "#6b7280" }}>
                    <p style={{ fontSize: "1.1rem" }}>No hay recetas registradas</p>
                </div>
            ) : (
                <div style={{ position: "relative", paddingLeft: "30px" }}>
                    <div style={{ position: "absolute", left: "15px", top: 0, bottom: 0, width: "2px", backgroundColor: "#e5e7eb" }}></div>

                    {prescriptions.map(prescription => (
                        <div key={prescription.id} style={{
                            position: "relative", backgroundColor: "white", border: "1px solid #e5e7eb",
                            borderRadius: "8px", padding: "20px", marginBottom: "20px", marginLeft: "20px",
                        }}>
                            <div style={{
                                position: "absolute", left: "-38px", top: "20px",
                                width: "16px", height: "16px", borderRadius: "50%",
                                backgroundColor: "#7c3aed", border: "3px solid white", boxShadow: "0 0 0 2px #7c3aed",
                            }} />

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                                <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
                                        <h3 style={{ margin: 0, color: "#1f2937" }}>{prescription.pet_name}</h3>
                                        <span style={{ padding: "2px 8px", backgroundColor: "#ede9fe", color: "#7c3aed", borderRadius: "4px", fontSize: "0.8rem" }}>
                                            {prescription.items.length} medicamento{prescription.items.length !== 1 ? "s" : ""}
                                        </span>
                                    </div>
                                    <p style={{ margin: 0, color: "#6b7280", fontSize: "0.9rem" }}>
                                        📅 {formatDate(prescription.created_at)} · Dr. {prescription.veterinarian_name}
                                    </p>
                                </div>
                                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                    <button onClick={() => handleView(prescription)}
                                        style={{ padding: "6px 12px", backgroundColor: "#3b82f6", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem" }}>
                                        Ver
                                    </button>
                                    <button
                                        onClick={() => handleDownloadPDF(prescription.id)}
                                        disabled={downloadingId === prescription.id}
                                        style={{ padding: "6px 12px", backgroundColor: "#7c3aed", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem", opacity: downloadingId === prescription.id ? 0.6 : 1 }}>
                                        {downloadingId === prescription.id ? "..." : "PDF"}
                                    </button>
                                    {canCreate && (
                                        <>
                                            <button onClick={() => handleEdit(prescription)}
                                                style={{ padding: "6px 12px", backgroundColor: "#6b7280", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem" }}>
                                                Editar
                                            </button>
                                            <button onClick={() => handleDelete(prescription.id)}
                                                style={{ padding: "6px 12px", backgroundColor: "#ef4444", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem" }}>
                                                Eliminar
                                            </button>
                                        </>
                                    )}
                                </div>
                            </div>

                            {prescription.items.length > 0 && (
                                <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                    {prescription.items.map((item, i) => (
                                        <span key={i} style={{ padding: "4px 10px", backgroundColor: "#f5f3ff", color: "#5b21b6", borderRadius: "4px", fontSize: "0.85rem" }}>
                                            {item.product_name} · {item.quantity} {item.product_unit}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Create/Edit Modal */}
            {showModal && (
                <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
                    <div style={{ backgroundColor: "white", padding: "25px", borderRadius: "10px", width: "600px", maxHeight: "90vh", overflowY: "auto" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "20px" }}>
                            <h3 style={{ margin: 0 }}>{editing ? "Editar Receta" : "Nueva Receta"}</h3>
                            <button onClick={closeModal} style={{ background: "none", border: "none", fontSize: "20px", cursor: "pointer" }}>✕</button>
                        </div>

                        <form onSubmit={handleSubmit}>
                            {error && <div style={{ backgroundColor: "#fee2e2", color: "#dc2626", padding: "10px", borderRadius: "5px", marginBottom: "15px" }}>{error}</div>}

                            <div style={{ marginBottom: "15px" }}>
                                <label style={{ fontWeight: "bold", display: "block", marginBottom: "5px" }}>Mascota *</label>
                                <select value={form.pet} onChange={e => setForm({ ...form, pet: e.target.value, medical_record: "" })}
                                    disabled={lockedFromParams}
                                    style={{ width: "100%", padding: "8px", borderRadius: "5px", border: "1px solid #ddd", backgroundColor: lockedFromParams ? "#f3f4f6" : "white" }}>
                                    <option value="">Seleccionar</option>
                                    {pets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                                </select>
                            </div>

                            <div style={{ marginBottom: "15px" }}>
                                <label style={{ fontWeight: "bold", display: "block", marginBottom: "5px" }}>Consulta médica *</label>
                                {!form.pet ? (
                                    <p style={{ margin: 0, color: "#9ca3af", fontSize: "0.9rem" }}>Selecciona una mascota primero</p>
                                ) : medicalRecordsForPet.filter(r => !r.prescription_id || String(r.id) === String(form.medical_record)).length === 0 ? (
                                    <p style={{ margin: 0, color: "#9ca3af", fontSize: "0.9rem" }}>Esta mascota no tiene consultas disponibles.</p>
                                ) : (
                                    <select value={form.medical_record} onChange={e => setForm({ ...form, medical_record: e.target.value })}
                                        disabled={lockedFromParams}
                                        style={{ width: "100%", padding: "8px", borderRadius: "5px", border: "1px solid #ddd", backgroundColor: lockedFromParams ? "#f3f4f6" : "white" }}>
                                        <option value="">Seleccionar consulta</option>
                                        {medicalRecordsForPet
                                            .filter(r => !r.prescription_id || String(r.id) === String(form.medical_record))
                                            .map(r => {
                                                const date = new Date(r.created_at).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
                                                const diag = (r.diagnosis || "").substring(0, 50);
                                                return <option key={r.id} value={r.id}>{date} — {diag}</option>;
                                            })
                                        }
                                    </select>
                                )}
                            </div>

                            {/* Medications */}
                            <div style={{ marginBottom: "15px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                                    <label style={{ fontWeight: "bold" }}>Medicamentos *</label>
                                    <button type="button" onClick={addItem}
                                        style={{ padding: "4px 12px", backgroundColor: "#4ecca3", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem" }}>
                                        + Agregar
                                    </button>
                                </div>

                                {form.items.map((item, index) => (
                                    <div key={index} style={{ backgroundColor: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: "8px", padding: "14px", marginBottom: "10px" }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                                            <span style={{ fontWeight: "bold", fontSize: "0.85rem", color: "#6b7280" }}>Medicamento {index + 1}</span>
                                            {form.items.length > 1 && (
                                                <button type="button" onClick={() => removeItem(index)}
                                                    style={{ padding: "2px 8px", backgroundColor: "#ef4444", color: "white", border: "none", borderRadius: "3px", cursor: "pointer", fontSize: "0.8rem" }}>
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "8px", marginBottom: "8px" }}>
                                            <div>
                                                <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "3px" }}>Producto *</label>
                                                <select value={item.product} onChange={e => updateItem(index, "product", e.target.value)}
                                                    style={{ width: "100%", padding: "7px", borderRadius: "4px", border: "1px solid #ddd" }}>
                                                    <option value="">Seleccionar producto</option>
                                                    {products.map(p => {
                                                        const pres = p.presentation || {};
                                                        return <option key={p.id} value={p.id}>{p.name} ({pres.base_unit_display || pres.base_unit || ""})</option>;
                                                    })}
                                                </select>
                                            </div>
                                            <div>
                                                <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "3px" }}>Cantidad *</label>
                                                <input type="number" step="0.01" min="0.01" value={item.quantity} onChange={e => updateItem(index, "quantity", e.target.value)}
                                                    placeholder="0"
                                                    style={{ width: "100%", padding: "7px", borderRadius: "4px", border: "1px solid #ddd", boxSizing: "border-box" }} />
                                            </div>
                                        </div>
                                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "8px" }}>
                                            <div>
                                                <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "3px" }}>Dosis *</label>
                                                <input type="text" value={item.dose} onChange={e => updateItem(index, "dose", e.target.value)}
                                                    placeholder="Ej: 1 comprimido cada 12h"
                                                    style={{ width: "100%", padding: "7px", borderRadius: "4px", border: "1px solid #ddd", boxSizing: "border-box" }} />
                                            </div>
                                            <div>
                                                <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "3px" }}>Duración</label>
                                                <input type="text" value={item.duration} onChange={e => updateItem(index, "duration", e.target.value)}
                                                    placeholder="Ej: 7 días"
                                                    style={{ width: "100%", padding: "7px", borderRadius: "4px", border: "1px solid #ddd", boxSizing: "border-box" }} />
                                            </div>
                                        </div>
                                        <div>
                                            <label style={{ fontSize: "0.8rem", color: "#6b7280", display: "block", marginBottom: "3px" }}>Instrucciones adicionales</label>
                                            <input type="text" value={item.instructions} onChange={e => updateItem(index, "instructions", e.target.value)}
                                                placeholder="Ej: Administrar con comida"
                                                style={{ width: "100%", padding: "7px", borderRadius: "4px", border: "1px solid #ddd", boxSizing: "border-box" }} />
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div style={{ marginBottom: "20px" }}>
                                <label style={{ fontWeight: "bold", display: "block", marginBottom: "5px" }}>Notas</label>
                                <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                                    placeholder="Observaciones adicionales..."
                                    style={{ width: "100%", padding: "8px", borderRadius: "5px", border: "1px solid #ddd", minHeight: "60px", boxSizing: "border-box" }} />
                            </div>

                            <div style={{ display: "flex", gap: "10px" }}>
                                <button type="submit" style={{ flex: 1, padding: "10px", backgroundColor: "#4ecca3", color: "white", border: "none", borderRadius: "5px", cursor: "pointer" }}>
                                    {editing ? "Guardar" : "Crear Receta"}
                                </button>
                                <button type="button" onClick={closeModal} style={{ flex: 1, padding: "10px", backgroundColor: "#6b7280", color: "white", border: "none", borderRadius: "5px", cursor: "pointer" }}>
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Detail Modal */}
            {showDetailModal && viewing && (
                <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
                    <div style={{ backgroundColor: "white", padding: "25px", borderRadius: "10px", width: "550px", maxHeight: "90vh", overflowY: "auto" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "20px" }}>
                            <h3 style={{ margin: 0 }}>Receta #{viewing.id}</h3>
                            <button onClick={() => { setShowDetailModal(false); setViewing(null); }} style={{ background: "none", border: "none", fontSize: "20px", cursor: "pointer" }}>✕</button>
                        </div>

                        <div style={{ display: "flex", gap: "20px", marginBottom: "16px" }}>
                            <div style={{ flex: 1 }}>
                                <p style={{ margin: "0 0 3px", fontSize: "0.8rem", color: "#6b7280" }}>Mascota</p>
                                <p style={{ margin: 0, fontWeight: "bold" }}>{viewing.pet_name}</p>
                            </div>
                            <div style={{ flex: 1 }}>
                                <p style={{ margin: "0 0 3px", fontSize: "0.8rem", color: "#6b7280" }}>Veterinario</p>
                                <p style={{ margin: 0 }}>Dr. {viewing.veterinarian_name}</p>
                            </div>
                            <div style={{ flex: 1 }}>
                                <p style={{ margin: "0 0 3px", fontSize: "0.8rem", color: "#6b7280" }}>Fecha</p>
                                <p style={{ margin: 0 }}>{formatDate(viewing.created_at)}</p>
                            </div>
                        </div>

                        <div style={{ marginBottom: "16px" }}>
                            <p style={{ margin: "0 0 10px", fontWeight: "bold" }}>Medicamentos recetados</p>
                            {viewing.items.map((item, i) => (
                                <div key={i} style={{ backgroundColor: "#f5f3ff", border: "1px solid #ddd6fe", borderRadius: "6px", padding: "12px", marginBottom: "8px" }}>
                                    <p style={{ margin: "0 0 6px", fontWeight: "bold", color: "#5b21b6" }}>
                                        {item.product_name} — {item.quantity} {item.product_unit}
                                    </p>
                                    <p style={{ margin: "0 0 3px", fontSize: "0.9rem" }}><strong>Dosis:</strong> {item.dose}</p>
                                    {item.duration && <p style={{ margin: "0 0 3px", fontSize: "0.9rem" }}><strong>Duración:</strong> {item.duration}</p>}
                                    {item.instructions && <p style={{ margin: 0, fontSize: "0.9rem", color: "#6b7280" }}>{item.instructions}</p>}
                                </div>
                            ))}
                        </div>

                        {viewing.notes && (
                            <div style={{ backgroundColor: "#fef3c7", border: "1px solid #fde68a", borderRadius: "6px", padding: "12px", marginBottom: "16px" }}>
                                <p style={{ margin: "0 0 4px", fontWeight: "bold", fontSize: "0.85rem" }}>Notas</p>
                                <p style={{ margin: 0, fontSize: "0.9rem" }}>{viewing.notes}</p>
                            </div>
                        )}

                        <div style={{ display: "flex", gap: "10px" }}>
                            <button
                                onClick={() => handleDownloadPDF(viewing.id)}
                                disabled={downloadingId === viewing.id}
                                style={{ flex: 1, padding: "10px", backgroundColor: "#7c3aed", color: "white", border: "none", borderRadius: "5px", cursor: "pointer", opacity: downloadingId === viewing.id ? 0.6 : 1 }}>
                                {downloadingId === viewing.id ? "Generando PDF..." : "Descargar PDF"}
                            </button>
                            <button onClick={() => { setShowDetailModal(false); setViewing(null); }}
                                style={{ flex: 1, padding: "10px", backgroundColor: "#6b7280", color: "white", border: "none", borderRadius: "5px", cursor: "pointer" }}>
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Prescriptions;
