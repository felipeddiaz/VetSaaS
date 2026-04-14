import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPet } from "../api/pets";
import { getMedicalRecords, getMedicalRecord } from "../api/medicalRecords";
import { useAuth } from "../auth/authContext";
import api from "../api/client";

const SEX_LABELS = { male: "Macho", female: "Hembra", unknown: "Desconocido" };

const PetDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { token, user, initializing } = useAuth();

    const [pet, setPet] = useState(null);
    const [records, setRecords] = useState([]);
    const [appointments, setAppointments] = useState([]);
    const [activeTab, setActiveTab] = useState("info");
    const [loading, setLoading] = useState(true);
    const [viewingRecord, setViewingRecord] = useState(null);
    const [showRecordDetail, setShowRecordDetail] = useState(false);

    useEffect(() => {
        if (token && id) loadAll();
    }, [token, id]);

    const loadAll = async () => {
        setLoading(true);
        try {
            const [petData, recordsData, apptData] = await Promise.all([
                getPet(id),
                getMedicalRecords(token, { pet: id }),
                api.get(`appointments/?pet=${id}`).then(r => r.data),
            ]);
            setPet(petData);
            setRecords(recordsData.results || recordsData);
            setAppointments(Array.isArray(apptData) ? apptData : (apptData.results || []));
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const calcAge = (birthDate) => {
        if (!birthDate) return null;
        const diff = Date.now() - new Date(birthDate).getTime();
        const years = Math.floor(diff / (1000 * 60 * 60 * 24 * 365.25));
        const months = Math.floor(diff / (1000 * 60 * 60 * 24 * 30.44));
        if (years >= 1) return `${years} año${years !== 1 ? "s" : ""}`;
        if (months >= 1) return `${months} mes${months !== 1 ? "es" : ""}`;
        return "< 1 mes";
    };

    const formatDate = (ds) => new Date(ds).toLocaleDateString("es-ES", { year: "numeric", month: "long", day: "numeric" });
    const formatDateTime = (ds) => new Date(ds).toLocaleDateString("es-ES", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

    const handleViewRecord = async (record) => {
        try {
            const data = await getMedicalRecord(token, record.id);
            setViewingRecord(data);
            setShowRecordDetail(true);
        } catch (err) {
            console.log(err);
        }
    };

    const STATUS_BADGE = {
        scheduled: "badge badge-info",
        done: "badge badge-success",
        canceled: "badge badge-danger",
    };
    const STATUS_LABEL = { scheduled: "Programada", done: "Completada", canceled: "Cancelada" };

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    if (!pet) {
        return (
            <div style={{ textAlign: "center", padding: "60px 20px" }}>
                <p style={{ color: "var(--c-text-2)", marginBottom: "16px" }}>Mascota no encontrada.</p>
                <button className="btn btn-secondary btn-md" onClick={() => navigate("/pets")}>
                    Volver a mascotas
                </button>
            </div>
        );
    }

    const canCreate = user?.role !== "ASSISTANT";

    return (
        <div>
            {/* Back + Header */}
            <button className="back-btn" onClick={() => navigate("/pets")}>
                ← Volver a mascotas
            </button>
            <div className="page-header">
                <div>
                    <h1 className="page-title">{pet.name}</h1>
                    <p className="page-subtitle">
                        {pet.species}{pet.breed ? ` · ${pet.breed}` : ""}
                        {pet.sex && pet.sex !== "unknown" ? ` · ${SEX_LABELS[pet.sex]}` : ""}
                        {calcAge(pet.birth_date) ? ` · ${calcAge(pet.birth_date)}` : ""}
                    </p>
                </div>
                {canCreate && (
                    <div style={{ display: "flex", gap: "8px" }}>
                        <button
                            className="btn btn-primary btn-md"
                            onClick={() => navigate(`/medical-records?pet=${pet.id}`)}
                        >
                            + Nueva Consulta
                        </button>
                        <button
                            className="btn btn-secondary btn-md"
                            onClick={() => navigate(`/appointments?pet=${pet.id}`)}
                        >
                            + Nueva Cita
                        </button>
                    </div>
                )}
            </div>

            {/* Tabs */}
            <div className="tabs">
                {[
                    { key: "info", label: "Información" },
                    { key: "records", label: `Historial (${records.length})` },
                    { key: "appointments", label: `Citas (${appointments.length})` },
                ].map(tab => (
                    <button
                        key={tab.key}
                        className={`tab-btn${activeTab === tab.key ? " active" : ""}`}
                        onClick={() => setActiveTab(tab.key)}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab: Info */}
            {activeTab === "info" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", maxWidth: "680px" }}>
                    <div className="card">
                        <p style={{ fontWeight: "600", marginBottom: "16px", fontSize: "13px" }}>Datos de la mascota</p>
                        {[
                            ["Nombre", pet.name],
                            ["Especie", pet.species],
                            ["Raza", pet.breed || "—"],
                            ["Fecha de nac.", pet.birth_date ? formatDate(pet.birth_date) : "—"],
                            ["Edad", calcAge(pet.birth_date) || "—"],
                            ["Sexo", SEX_LABELS[pet.sex] || "—"],
                            ["Color", pet.color || "—"],
                        ].map(([label, value]) => value && (
                            <div key={label} className="info-row">
                                <span className="info-row-label">{label}</span>
                                <span className="info-row-value">{value}</span>
                            </div>
                        ))}
                    </div>
                    <div className="card">
                        <p style={{ fontWeight: "600", marginBottom: "16px", fontSize: "13px" }}>Propietario</p>
                        <div className="info-row">
                            <span className="info-row-label">Nombre</span>
                            <span className="info-row-value">{pet.owner?.name || "—"}</span>
                        </div>
                        <div className="info-row">
                            <span className="info-row-label">Teléfono</span>
                            <span className="info-row-value">{pet.owner?.phone || "—"}</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Tab: Historial */}
            {activeTab === "records" && (
                records.length === 0 ? (
                    <div className="empty-state">
                        <p className="empty-state-title">Esta mascota no tiene consultas registradas.</p>
                        {canCreate && (
                            <button
                                className="btn btn-primary btn-md"
                                style={{ marginTop: "14px" }}
                                onClick={() => navigate(`/medical-records?pet=${pet.id}`)}
                            >
                                Registrar primera consulta
                            </button>
                        )}
                    </div>
                ) : (
                    <div className="timeline">
                        {records.map(record => (
                            <div key={record.id} className="timeline-item card card-hover">
                                <div className="timeline-dot" />
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                    <div style={{ flex: 1, marginRight: "16px" }}>
                                        <p style={{ fontWeight: "600", marginBottom: "4px" }}>{formatDateTime(record.created_at)}</p>
                                        <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", marginBottom: "8px" }}>
                                            Dr. {record.veterinarian_name || "—"}
                                            {record.weight && ` · ${record.weight} kg`}
                                            {record.prescription_id && (
                                                <span className="badge badge-purple" style={{ marginLeft: "8px" }}>Receta</span>
                                            )}
                                        </p>
                                        <p style={{ fontSize: "13.5px", color: "var(--c-text)" }}>
                                            {record.diagnosis.length > 90 ? record.diagnosis.slice(0, 90) + "…" : record.diagnosis}
                                        </p>
                                    </div>
                                    <button
                                        className="btn btn-info btn-sm"
                                        style={{ flexShrink: 0 }}
                                        onClick={() => handleViewRecord(record)}
                                    >
                                        Ver
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )
            )}

            {/* Tab: Citas */}
            {activeTab === "appointments" && (
                appointments.length === 0 ? (
                    <div className="empty-state">
                        <p className="empty-state-title">Esta mascota no tiene citas registradas.</p>
                    </div>
                ) : (
                    <div style={{ display: "grid", gap: "10px" }}>
                        {appointments.map(appt => (
                            <div key={appt.id} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                                        <span style={{ fontWeight: "600" }}>
                                            {new Date(appt.date).toLocaleDateString("es-ES", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
                                        </span>
                                        <span className={STATUS_BADGE[appt.status] || "badge badge-default"}>
                                            {STATUS_LABEL[appt.status]}
                                        </span>
                                    </div>
                                    <p style={{ fontSize: "12.5px", color: "var(--c-text-2)" }}>
                                        {appt.start_time?.slice(0, 5)} – {appt.end_time?.slice(0, 5)}
                                        {appt.veterinarian_name && ` · Dr. ${appt.veterinarian_name}`}
                                    </p>
                                    {appt.reason && <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", marginTop: "4px" }}>{appt.reason}</p>}
                                </div>
                            </div>
                        ))}
                    </div>
                )
            )}

            {/* Record Detail Modal */}
            {showRecordDetail && viewingRecord && (
                <div className="modal-overlay">
                    <div className="modal modal-md">
                        <div className="modal-header">
                            <h3>Detalle de Consulta</h3>
                            <button className="modal-close" onClick={() => { setShowRecordDetail(false); setViewingRecord(null); }}>✕</button>
                        </div>
                        <div className="modal-body">
                            <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", marginBottom: "20px" }}>
                                {formatDateTime(viewingRecord.created_at)} · Dr. {viewingRecord.veterinarian_name || "—"}
                                {viewingRecord.weight && ` · ${viewingRecord.weight} kg`}
                            </p>

                            <div className="form-group">
                                <label className="form-label">DIAGNÓSTICO</label>
                                <div className="card" style={{ background: "var(--c-subtle)", padding: "12px" }}>
                                    <p style={{ whiteSpace: "pre-wrap", fontSize: "13.5px" }}>{viewingRecord.diagnosis}</p>
                                </div>
                            </div>
                            <div className="form-group">
                                <label className="form-label">TRATAMIENTO</label>
                                <div className="card" style={{ background: "var(--c-success-bg)", borderColor: "var(--c-success-border)", padding: "12px" }}>
                                    <p style={{ whiteSpace: "pre-wrap", fontSize: "13.5px" }}>{viewingRecord.treatment}</p>
                                </div>
                            </div>
                            {viewingRecord.notes && (
                                <div className="form-group">
                                    <label className="form-label">NOTAS</label>
                                    <div className="card" style={{ background: "var(--c-warning-bg)", borderColor: "var(--c-warning-border)", padding: "12px" }}>
                                        <p style={{ whiteSpace: "pre-wrap", fontSize: "13.5px" }}>{viewingRecord.notes}</p>
                                    </div>
                                </div>
                            )}
                            {viewingRecord.products_used?.length > 0 && (
                                <div>
                                    <label className="form-label">PRODUCTOS UTILIZADOS</label>
                                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                        {viewingRecord.products_used.map((p, i) => (
                                            <span key={i} className="badge badge-success" style={{ height: "auto", padding: "4px 10px" }}>
                                                {p.product_name} · {p.quantity} {p.base_unit_display || p.base_unit || ""}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="modal-footer">
                            {viewingRecord.prescription_id ? (
                                <button
                                    className="btn btn-purple btn-md"
                                    onClick={() => { setShowRecordDetail(false); navigate(`/prescriptions?medical_record=${viewingRecord.id}&pet=${pet.id}`); }}
                                >
                                    Ver Receta
                                </button>
                            ) : canCreate ? (
                                <button
                                    className="btn btn-purple btn-md"
                                    onClick={() => { setShowRecordDetail(false); navigate(`/prescriptions?medical_record=${viewingRecord.id}&pet=${pet.id}`); }}
                                >
                                    Crear Receta
                                </button>
                            ) : null}
                            <button
                                className="btn btn-secondary btn-md"
                                style={{ marginLeft: "auto" }}
                                onClick={() => { setShowRecordDetail(false); setViewingRecord(null); }}
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PetDetail;
