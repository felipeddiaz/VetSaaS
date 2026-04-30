import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useConfirm } from "../components/ConfirmDialog";
import { toast } from "sonner";
import { Icon } from "../components/icons";
import PrescriptionForm from "../components/prescriptions/PrescriptionForm";
import { useAuth } from "../auth/authContext";
import { getProducts } from "../api/inventory";
import { getMedicalRecords } from "../api/medicalRecords";
import { getPets } from "../api/pets";
import {
    createPrescription,
    deletePrescription,
    downloadPrescriptionPDF,
    getPrescription,
    getPrescriptions,
    updatePrescription,
} from "../api/prescriptions";

const Prescriptions = () => {
    const { token, user, initializing } = useAuth();
    const confirm = useConfirm();
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
    const [formSeed, setFormSeed] = useState({ medical_record: "", pet: "", notes: "", items: [] });

    const [downloadingId, setDownloadingId] = useState(null);

    const canCreate = user?.role !== "ASSISTANT";

    const loadPrescriptions = useCallback(async () => {
        try {
            const params = {};
            if (selectedPet) params.pet = selectedPet;
            const data = await getPrescriptions(params);
            setPrescriptions(data);
        } catch (err) {
            console.log(err);
        }
    }, [selectedPet]);

    const loadMedicalRecordsForPet = useCallback(async (petId) => {
        if (!petId || !token) {
            setMedicalRecordsForPet([]);
            return;
        }
        try {
            const data = await getMedicalRecords(token, { pet: petId });
            setMedicalRecordsForPet(data.results || data);
        } catch {
            setMedicalRecordsForPet([]);
        }
    }, [token]);

    useEffect(() => {
        if (!token) return;
        const loadAll = async () => {
            setLoading(true);
            try {
                const [petsData, prodsData] = await Promise.all([
                    getPets(),
                    getProducts({ active: "true" }),
                ]);
                setPets(Array.isArray(petsData) ? petsData : (petsData.results || []));
                setProducts(Array.isArray(prodsData) ? prodsData : (prodsData.results || []));
                await loadPrescriptions();
            } catch (err) {
                console.log(err);
            } finally {
                setLoading(false);
            }
        };
        loadAll();
    }, [token, loadPrescriptions]);

    useEffect(() => {
        if (token) loadPrescriptions();
    }, [token, loadPrescriptions]);

    useEffect(() => {
        const mrParam = searchParams.get("medical_record");
        const petParam = searchParams.get("pet");
        if (mrParam && petParam && token) {
            setLockedFromParams(true);
            setEditing(null);
            setFormSeed({ medical_record: mrParam, pet: petParam, notes: "", items: [] });
            setShowModal(true);
        }
    }, [searchParams, token]);

    const closeModal = () => {
        setShowModal(false);
        setEditing(null);
        setLockedFromParams(false);
        setMedicalRecordsForPet([]);
        setFormSeed({ medical_record: "", pet: "", notes: "", items: [] });
    };

    const handleCreate = () => {
        setEditing(null);
        setLockedFromParams(false);
        setFormSeed({ medical_record: "", pet: "", notes: "", items: [] });
        setShowModal(true);
    };

    const handleFormSubmit = async (payload) => {
        if (editing) {
            await updatePrescription(editing.id, payload);
            toast.success("Receta actualizada");
        } else {
            await createPrescription(payload);
            toast.success("Receta creada");
        }
        await loadPrescriptions();
        closeModal();
    };

    const handleView = async (prescription) => {
        try {
            const data = await getPrescription(prescription.id);
            setViewing(data);
            setShowDetailModal(true);
        } catch {
            toast.error("Error al cargar la receta");
        }
    };

    const handleEdit = async (prescription) => {
        setEditing(prescription);
        setLockedFromParams(false);
        setFormSeed({
            medical_record: prescription.medical_record || "",
            pet: prescription.pet,
            notes: prescription.notes || "",
            items: prescription.items || [],
        });
        await loadMedicalRecordsForPet(prescription.pet);
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        const ok = await confirm({
            message: "¿Eliminar esta receta? El registro médico asociado no se verá afectado.",
            confirmText: "Eliminar",
            dangerMode: true,
        });
        if (!ok) return;
        try {
            await deletePrescription(id);
            toast.success("Receta eliminada");
            loadPrescriptions();
        } catch {
            toast.error("Error al eliminar la receta");
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
        } catch {
            toast.error("Error al generar el PDF");
        } finally {
            setDownloadingId(null);
        }
    };

    const formatDate = (dateString) => new Date(dateString).toLocaleDateString("es-ES", { year: "numeric", month: "long", day: "numeric" });

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p>Cargando...</p>
            </div>
        );
    }

    return (
        <div style={{ padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
                <div>
                    <h2 style={{ margin: 0 }}>Recetas Médicas</h2>
                    <p style={{ margin: "6px 0 0", color: "#6b7280", fontSize: "0.92rem" }}>
                        Vista secundaria para consultar, reimprimir o editar recetas ya emitidas.
                    </p>
                </div>
                {canCreate && (
                    <button
                        onClick={handleCreate}
                        style={{ padding: "10px 20px", backgroundColor: "#4ecca3", color: "white", border: "none", borderRadius: "5px", cursor: "pointer" }}
                    >
                        + Nueva Receta
                    </button>
                )}
            </div>

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
                                        <Icon.CalendarDays s={13} /> {formatDate(prescription.created_at)} · Dr. {prescription.veterinarian_name}
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

            {showModal && (
                <PrescriptionForm
                    title={editing ? "Editar Receta" : "Nueva Receta"}
                    initialValue={formSeed}
                    pets={pets}
                    products={products}
                    medicalRecordsForPet={medicalRecordsForPet}
                    lockedPet={lockedFromParams}
                    lockedMedicalRecord={lockedFromParams}
                    submitLabel={editing ? "Guardar" : "Crear Receta"}
                    onPetChange={loadMedicalRecordsForPet}
                    onSubmit={handleFormSubmit}
                    onCancel={closeModal}
                />
            )}

            {showDetailModal && viewing && (
                <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
                    <div style={{ backgroundColor: "white", padding: "25px", borderRadius: "10px", width: "550px", maxHeight: "90vh", overflowY: "auto" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "20px" }}>
                            <h3 style={{ margin: 0 }}>Receta #{viewing.id}</h3>
                            <button onClick={() => { setShowDetailModal(false); setViewing(null); }} style={{ background: "none", border: "none", fontSize: "20px", cursor: "pointer" }}><Icon.X s={16} /></button>
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
