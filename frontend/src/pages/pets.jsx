import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dog as LucideDog } from "lucide-react";
import { getPets, createPet, updatePet, deletePet } from "../api/pets";
import { getMedicalRecords } from "../api/medicalRecords";
import { getAppointments } from "../api/appointments";
import { useAuth } from "../auth/authContext";

// ─── Constants ────────────────────────────────────────────────────────────────
const SEX_LABELS = { male: "Macho", female: "Hembra", unknown: "Desconocido" };

const EMPTY_FORM = {
    name: "", species: "", breed: "", birth_date: "",
    sex: "unknown", color: "",
    owner: { name: "", phone: "" },
};

// ─── Species detection ────────────────────────────────────────────────────────
const isCanino = (p) => /perro|canino|dog/i.test(p.species);
const isFelino = (p) => /gato|felino|cat/i.test(p.species);

// ─── Age utilities ────────────────────────────────────────────────────────────
const calcAge = (bd) => {
    if (!bd) return null;
    const ms = Date.now() - new Date(bd).getTime();
    const y = Math.floor(ms / (365.25 * 24 * 3600 * 1000));
    const m = Math.floor(ms / (30.44 * 24 * 3600 * 1000));
    if (y >= 1) return `${y} año${y !== 1 ? "s" : ""}`;
    if (m >= 1) return `${m} mes${m !== 1 ? "es" : ""}`;
    return "< 1 mes";
};

const getAgeYears = (bd) => {
    if (!bd) return null;
    return (Date.now() - new Date(bd).getTime()) / (365.25 * 24 * 3600 * 1000);
};

const getAgeGroup = (bd) => {
    const y = getAgeYears(bd);
    if (y === null) return null;
    if (y < 1) return "cachorro";
    if (y < 3) return "joven";
    if (y < 8) return "adulto";
    return "senior";
};

// ─── Week range ───────────────────────────────────────────────────────────────
const getWeekRange = () => {
    const now = new Date();
    const start = new Date(now);
    start.setDate(now.getDate() - now.getDay());
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    end.setHours(23, 59, 59, 999);
    return { start, end };
};

// ─── SVG Icons ────────────────────────────────────────────────────────────────
const Ic = {
    Bone: ({ s = 20, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 10c.7-.7 1.69 0 2.5 0a2.5 2.5 0 1 0 0-5 .5.5 0 0 1-.5-.5 2.5 2.5 0 1 0-5 0c0 .81.7 1.8 0 2.5l-4.6 4.6c-.7.7-1.69 0-2.5 0a2.5 2.5 0 1 0 0 5 .5.5 0 0 1 .5.5 2.5 2.5 0 1 0 5 0c0-.81-.7-1.8 0-2.5Z" />
        </svg>
    ),
    Cat: ({ s = 20, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21s-9-3-9-7.56c0-1.25.5-2.4 1-3.44 0 0-1.89-6.42-.5-7 1.39-.58 4.68.2 6.51 2.26A9.06 9.06 0 0 1 12 5z" />
            <path d="M8 14v.5M16 14v.5" />
            <path d="M11.25 16.25h1.5L12 17l-.75-.75z" />
        </svg>
    ),
    Dog: ({ s = 20, c = "currentColor" }) => (
        <LucideDog size={s} color={c} strokeWidth={2} />
    ),
    Paw: ({ s = 20, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="4" r="2" />
            <circle cx="18" cy="8" r="2" />
            <circle cx="4" cy="8" r="2" />
            <path d="M9.37 17.74a3.5 3.5 0 0 0 5.26 0L17 14.5a3.5 3.5 0 0 0-2.63-5.87 3.5 3.5 0 0 0-2.37.93 3.5 3.5 0 0 0-2.37-.93A3.5 3.5 0 0 0 7 14.5z" />
        </svg>
    ),
    Calendar: ({ s = 18, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
    ),
    Search: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
    ),
    Grid: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
    ),
    Rows: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="18" height="4" rx="1" />
            <rect x="3" y="11" width="18" height="4" rx="1" />
            <rect x="3" y="17" width="18" height="4" rx="1" />
        </svg>
    ),
    X: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
    ),
    User: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
        </svg>
    ),
    Phone: ({ s = 13, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.6 1.18h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.96a16 16 0 0 0 6.13 6.13l1.36-1.36a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
        </svg>
    ),
    Syringe: ({ s = 14, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m18 2 4 4" />
            <path d="m17 7 3-3" />
            <path d="M19 9 8.7 19.3a1 1 0 0 1-1.4 0l-2.6-2.6a1 1 0 0 1 0-1.4L15 5" />
            <path d="m9 11 4 4" />
            <path d="m5 19-3 3" />
            <path d="m14 4 6 6" />
        </svg>
    ),
    TrendUp: ({ s = 13, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
        </svg>
    ),
    Edit: ({ s = 13, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
    ),
    Trash: ({ s = 13, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14H6L5 6" />
            <path d="M10 11v6M14 11v6M9 6V4h6v2" />
        </svg>
    ),
    ChevronRight: ({ s = 15, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
        </svg>
    ),
    AlertTriangle: ({ s = 14, c = "currentColor" }) => (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
    ),
};

// ─── Species Icon helper ──────────────────────────────────────────────────────
const SpeciesIcon = ({ pet, size = 20, color }) => {
    if (isCanino(pet)) return <Ic.Bone s={size} c={color} />;
    if (isFelino(pet)) return <Ic.Cat s={size} c={color} />;
    return <Ic.Paw s={size} c={color} />;
};

const speciesAccent = (pet) => isCanino(pet)
    ? { bg: "#dbeafe", icon: "#3b82f6", border: "#bfdbfe", text: "#1d4ed8" }
    : isFelino(pet)
    ? { bg: "#fce7f3", icon: "#ec4899", border: "#fbcfe8", text: "#be185d" }
    : { bg: "var(--c-primary-light)", icon: "var(--c-primary-dark)", border: "#99f6e4", text: "var(--c-primary-dark)" };

// ─── Pet Form Modal ───────────────────────────────────────────────────────────
const PetModal = ({ form, setForm, editing, onSubmit, onClose, error }) => (
    <div className="modal-overlay">
        <div className="modal modal-md">
            <div className="modal-header">
                <h3>{editing ? "Editar Mascota" : "Nueva Mascota"}</h3>
                <button className="modal-close" onClick={onClose}><Ic.X s={16} /></button>
            </div>
            <div className="modal-body">
                {error && <div className="alert alert-danger" style={{ marginBottom: "16px" }}>{error}</div>}
                <form onSubmit={onSubmit}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
                        <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                            <label className="form-label">NOMBRE *</label>
                            <input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Ej: Max" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">ESPECIE *</label>
                            <input className="input" value={form.species} onChange={e => setForm({ ...form, species: e.target.value })} placeholder="Ej: Perro, Gato" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">RAZA</label>
                            <input className="input" value={form.breed} onChange={e => setForm({ ...form, breed: e.target.value })} placeholder="Ej: Labrador" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">FECHA DE NACIMIENTO</label>
                            <input type="date" className="input" value={form.birth_date} onChange={e => setForm({ ...form, birth_date: e.target.value })} />
                        </div>
                        <div className="form-group">
                            <label className="form-label">SEXO</label>
                            <select className="select-input" value={form.sex} onChange={e => setForm({ ...form, sex: e.target.value })}>
                                <option value="unknown">Desconocido</option>
                                <option value="male">Macho</option>
                                <option value="female">Hembra</option>
                            </select>
                        </div>
                        <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                            <label className="form-label">COLOR</label>
                            <input className="input" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })} placeholder="Ej: Café con blanco" />
                        </div>
                    </div>
                    <hr className="divider" />
                    <p style={{ fontSize: "12.5px", fontWeight: "600", color: "var(--c-text-2)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Propietario
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
                        <div className="form-group">
                            <label className="form-label">NOMBRE *</label>
                            <input className="input" value={form.owner.name} onChange={e => setForm({ ...form, owner: { ...form.owner, name: e.target.value } })} placeholder="Nombre del dueño" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">TELÉFONO</label>
                            <input className="input" value={form.owner.phone} onChange={e => setForm({ ...form, owner: { ...form.owner, phone: e.target.value } })} placeholder="Teléfono" />
                        </div>
                    </div>
                </form>
            </div>
            <div className="modal-footer">
                <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={onSubmit}>
                    {editing ? "Guardar cambios" : "Registrar mascota"}
                </button>
                <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={onClose}>Cancelar</button>
            </div>
        </div>
    </div>
);

// ─── Pet Card ─────────────────────────────────────────────────────────────────
const PetCard = ({ pet, onSelect, onEdit, onDelete }) => {
    const age = calcAge(pet.birth_date);
    const ageGroup = getAgeGroup(pet.birth_date);
    const accent = speciesAccent(pet);

    const ageBadgeClass = ageGroup === "senior" ? "badge-warning"
        : ageGroup === "cachorro" ? "badge-info"
        : "badge-default";

    return (
        <div
            className="card card-hover"
            style={{ cursor: "pointer", padding: "18px 20px" }}
            onClick={onSelect}
        >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: "12px", marginBottom: "14px" }}>
                <div style={{
                    width: "44px", height: "44px", borderRadius: "12px", flexShrink: 0,
                    background: accent.bg, border: `1px solid ${accent.border}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                    <SpeciesIcon pet={pet} size={22} color={accent.icon} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <h3 style={{ fontSize: "15px", fontWeight: "700", marginBottom: "2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {pet.name}
                    </h3>
                    <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {pet.species}{pet.breed ? ` · ${pet.breed}` : ""}
                    </p>
                </div>
                {ageGroup && (
                    <span className={`badge ${ageBadgeClass}`} style={{ flexShrink: 0 }}>
                        {ageGroup.charAt(0).toUpperCase() + ageGroup.slice(1)}
                    </span>
                )}
            </div>

            {/* Data grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
                <div>
                    <p style={{ fontSize: "10.5px", color: "var(--c-text-3)", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "2px" }}>Edad</p>
                    <p style={{ fontSize: "13px", color: "var(--c-text-2)" }}>{age || "—"}</p>
                </div>
                <div>
                    <p style={{ fontSize: "10.5px", color: "var(--c-text-3)", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "2px" }}>Sexo</p>
                    <p style={{ fontSize: "13px", color: "var(--c-text-2)" }}>
                        {pet.sex && pet.sex !== "unknown" ? SEX_LABELS[pet.sex] : "—"}
                    </p>
                </div>
                {pet.color && (
                    <div style={{ gridColumn: "1 / -1" }}>
                        <p style={{ fontSize: "10.5px", color: "var(--c-text-3)", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "2px" }}>Color</p>
                        <p style={{ fontSize: "13px", color: "var(--c-text-2)" }}>{pet.color}</p>
                    </div>
                )}
            </div>

            {/* Owner */}
            <div style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "8px 10px", borderRadius: "var(--r-md)",
                background: "var(--c-subtle)", marginBottom: "12px",
            }}>
                <Ic.User s={14} c="var(--c-text-3)" />
                <div style={{ minWidth: 0 }}>
                    <p style={{ fontSize: "12.5px", fontWeight: "500", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {pet.owner?.name || "Sin propietario"}
                    </p>
                    {pet.owner?.phone && (
                        <p style={{ fontSize: "11.5px", color: "var(--c-text-3)" }}>{pet.owner.phone}</p>
                    )}
                </div>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: "6px" }} onClick={e => e.stopPropagation()}>
                <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => onEdit(pet)}>
                    <Ic.Edit s={13} /> Editar
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => onDelete(pet.id)}>
                    <Ic.Trash s={13} />
                </button>
            </div>
        </div>
    );
};

// ─── Quick Profile Panel ──────────────────────────────────────────────────────
const QuickPanel = ({ pet, records, appointments, loading, onClose, onEdit, navigate }) => {
    if (!pet) return null;

    const accent = speciesAccent(pet);
    const age = calcAge(pet.birth_date);
    const ageGroup = getAgeGroup(pet.birth_date);

    // Sort records by date desc
    const sortedRecords = [...records].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    // Vaccine records: treatment or diagnosis mentions "vacun"
    const vaccineRecords = sortedRecords.filter(r =>
        /vacun/i.test(r.diagnosis || "") ||
        /vacun/i.test(r.treatment || "") ||
        /vacun/i.test(r.notes || "")
    );
    const lastVaccine = vaccineRecords[0] || null;

    // Upcoming scheduled appointments
    const now = new Date();
    const upcoming = appointments
        .filter(a => a.status === "scheduled" && new Date(a.date) >= now)
        .sort((a, b) => new Date(a.date) - new Date(b.date))
        .slice(0, 2);

    const fmtDate = (ds) => new Date(ds).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" });
    const fmtWeekday = (ds) => new Date(ds).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });

    return (
        <>
            {/* Backdrop */}
            <div
                onClick={onClose}
                style={{
                    position: "fixed", inset: 0,
                    background: "rgba(15,23,42,0.28)",
                    zIndex: 900,
                    animation: "fadeIn 0.15s ease",
                }}
            />

            {/* Panel */}
            <div style={{
                position: "fixed", top: 0, right: 0, bottom: 0,
                width: "390px", maxWidth: "100vw",
                background: "var(--c-surface)",
                borderLeft: "1px solid var(--c-border)",
                zIndex: 910,
                display: "flex", flexDirection: "column",
                boxShadow: "-8px 0 40px rgba(0,0,0,0.10)",
                animation: "slideInRight 0.22s ease",
            }}>

                {/* Header */}
                <div style={{
                    padding: "20px 22px 16px",
                    borderBottom: "1px solid var(--c-border)",
                    display: "flex", alignItems: "flex-start", gap: "14px",
                    flexShrink: 0,
                }}>
                    <div style={{
                        width: "52px", height: "52px", borderRadius: "14px", flexShrink: 0,
                        background: accent.bg, border: `1px solid ${accent.border}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <SpeciesIcon pet={pet} size={26} color={accent.icon} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <h3 style={{ fontSize: "17px", fontWeight: "700", marginBottom: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {pet.name}
                        </h3>
                        <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", marginBottom: "7px" }}>
                            {pet.species}{pet.breed ? ` · ${pet.breed}` : ""}
                        </p>
                        <div style={{ display: "flex", gap: "5px", flexWrap: "wrap" }}>
                            {age && <span className="badge badge-default">{age}</span>}
                            {pet.sex && pet.sex !== "unknown" && (
                                <span className="badge badge-default">{SEX_LABELS[pet.sex]}</span>
                            )}
                            {ageGroup && (
                                <span className={`badge ${ageGroup === "senior" ? "badge-warning" : ageGroup === "cachorro" ? "badge-info" : "badge-default"}`}>
                                    {ageGroup.charAt(0).toUpperCase() + ageGroup.slice(1)}
                                </span>
                            )}
                        </div>
                    </div>
                    <button
                        className="btn btn-ghost"
                        style={{ padding: "6px", flexShrink: 0 }}
                        onClick={onClose}
                    >
                        <Ic.X s={15} />
                    </button>
                </div>

                {/* Body */}
                <div style={{ flex: 1, overflowY: "auto", padding: "20px 22px" }}>
                    {loading ? (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "120px" }}>
                            <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando datos...</p>
                        </div>
                    ) : (
                        <>
                            {/* Propietario */}
                            <section style={{ marginBottom: "22px" }}>
                                <p style={sectionTitle}>Propietario</p>
                                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                    <div style={{
                                        width: "36px", height: "36px", borderRadius: "50%", flexShrink: 0,
                                        background: "var(--c-subtle)", border: "1px solid var(--c-border)",
                                        display: "flex", alignItems: "center", justifyContent: "center",
                                    }}>
                                        <Ic.User s={16} c="var(--c-text-2)" />
                                    </div>
                                    <div>
                                        <p style={{ fontWeight: "600", fontSize: "13.5px" }}>{pet.owner?.name || "—"}</p>
                                        {pet.owner?.phone && (
                                            <p style={{ fontSize: "12px", color: "var(--c-text-2)", display: "flex", alignItems: "center", gap: "4px", marginTop: "2px" }}>
                                                <Ic.Phone s={12} c="var(--c-text-3)" />
                                                {pet.owner.phone}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </section>

                            {/* Datos físicos */}
                            {(pet.color || pet.birth_date) && (
                                <section style={{ marginBottom: "22px" }}>
                                    <p style={sectionTitle}>Datos físicos</p>
                                    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                                        {pet.birth_date && (
                                            <div className="info-row" style={{ marginBottom: 0 }}>
                                                <span className="info-row-label">Fecha nac.</span>
                                                <span className="info-row-value">
                                                    {new Date(pet.birth_date).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" })}
                                                </span>
                                            </div>
                                        )}
                                        {pet.color && (
                                            <div className="info-row" style={{ marginBottom: 0 }}>
                                                <span className="info-row-label">Color</span>
                                                <span className="info-row-value">{pet.color}</span>
                                            </div>
                                        )}
                                    </div>
                                </section>
                            )}

                            {/* Próximas citas */}
                            {upcoming.length > 0 && (
                                <section style={{ marginBottom: "22px" }}>
                                    <p style={sectionTitle}>Próximas citas</p>
                                    <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                                        {upcoming.map(appt => (
                                            <div key={appt.id} style={{
                                                display: "flex", alignItems: "flex-start", gap: "10px",
                                                padding: "10px 12px", borderRadius: "var(--r-md)",
                                                background: "var(--c-info-bg)", border: "1px solid var(--c-info-border)",
                                            }}>
                                                <Ic.Calendar s={14} c="var(--c-info-text)" />
                                                <div>
                                                    <p style={{ fontWeight: "600", fontSize: "12.5px", color: "var(--c-info-text)" }}>
                                                        {fmtWeekday(appt.date)}
                                                    </p>
                                                    <p style={{ fontSize: "11.5px", color: "var(--c-text-2)", marginTop: "1px" }}>
                                                        {appt.start_time?.slice(0, 5)}{appt.veterinarian_name ? ` · Dr. ${appt.veterinarian_name}` : ""}
                                                        {appt.reason ? ` · ${appt.reason}` : ""}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </section>
                            )}

                            {/* Historial reciente */}
                            <section style={{ marginBottom: "22px" }}>
                                <p style={sectionTitle}>Historial reciente</p>
                                {sortedRecords.length === 0 ? (
                                    <p style={{ fontSize: "12.5px", color: "var(--c-text-3)", fontStyle: "italic" }}>Sin consultas registradas</p>
                                ) : (
                                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                                        {sortedRecords.slice(0, 3).map(rec => (
                                            <div key={rec.id} style={{
                                                padding: "10px 12px", borderRadius: "var(--r-md)",
                                                border: "1px solid var(--c-border)", background: "var(--c-subtle)",
                                            }}>
                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                                                    <span style={{ fontSize: "11.5px", fontWeight: "600", color: "var(--c-text-2)" }}>
                                                        {fmtDate(rec.created_at)}
                                                    </span>
                                                    {rec.veterinarian_name && (
                                                        <span style={{ fontSize: "11px", color: "var(--c-text-3)" }}>Dr. {rec.veterinarian_name}</span>
                                                    )}
                                                </div>
                                                <p style={{ fontSize: "12.5px", color: "var(--c-text)", lineHeight: "1.45" }}>
                                                    {rec.diagnosis?.length > 75 ? rec.diagnosis.slice(0, 75) + "…" : rec.diagnosis}
                                                </p>
                                                {rec.weight && (
                                                    <p style={{ fontSize: "11px", color: "var(--c-text-3)", marginTop: "4px" }}>{rec.weight} kg</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </section>

                            {/* Estado de vacunas */}
                            <section style={{ marginBottom: "4px" }}>
                                <p style={sectionTitle}>Estado de vacunas</p>
                                {lastVaccine ? (
                                    <div style={{
                                        display: "flex", alignItems: "center", gap: "10px",
                                        padding: "10px 12px", borderRadius: "var(--r-md)",
                                        background: "var(--c-success-bg)", border: "1px solid var(--c-success-border)",
                                    }}>
                                        <Ic.Syringe s={14} c="var(--c-success-text)" />
                                        <div>
                                            <p style={{ fontSize: "12.5px", fontWeight: "600", color: "var(--c-success-text)" }}>Último registro de vacunación</p>
                                            <p style={{ fontSize: "11.5px", color: "var(--c-success-text)", opacity: 0.85, marginTop: "1px" }}>
                                                {fmtDate(lastVaccine.created_at)}
                                                {lastVaccine.veterinarian_name ? ` · Dr. ${lastVaccine.veterinarian_name}` : ""}
                                            </p>
                                        </div>
                                    </div>
                                ) : sortedRecords.length === 0 ? (
                                    <p style={{ fontSize: "12.5px", color: "var(--c-text-3)", fontStyle: "italic" }}>Sin historial clínico registrado</p>
                                ) : (
                                    <div style={{
                                        display: "flex", alignItems: "center", gap: "10px",
                                        padding: "10px 12px", borderRadius: "var(--r-md)",
                                        background: "var(--c-warning-bg)", border: "1px solid var(--c-warning-border)",
                                    }}>
                                        <Ic.AlertTriangle s={14} c="var(--c-warning-text)" />
                                        <p style={{ fontSize: "12.5px", color: "var(--c-warning-text)" }}>
                                            Sin registros de vacunación en el historial
                                        </p>
                                    </div>
                                )}
                            </section>
                        </>
                    )}
                </div>

                {/* Footer */}
                <div style={{
                    padding: "14px 22px", borderTop: "1px solid var(--c-border)",
                    display: "flex", gap: "8px", flexShrink: 0,
                }}>
                    <button
                        className="btn btn-primary btn-md"
                        style={{ flex: 1 }}
                        onClick={() => { onClose(); navigate(`/pets/${pet.id}`); }}
                    >
                        Ver ficha completa
                        <Ic.ChevronRight s={14} />
                    </button>
                    <button
                        className="btn btn-secondary btn-md"
                        onClick={() => { onClose(); onEdit(pet); }}
                    >
                        <Ic.Edit s={14} />
                        Editar
                    </button>
                </div>
            </div>
        </>
    );
};

// Shared section title style
const sectionTitle = {
    fontSize: "11px", fontWeight: "700", color: "var(--c-text-3)",
    textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "10px",
};

// ─── Main Component ───────────────────────────────────────────────────────────
const Pets = () => {
    const { token, initializing } = useAuth();
    const navigate = useNavigate();

    const [pets, setPets] = useState([]);
    const [weekAppts, setWeekAppts] = useState([]);
    const [loading, setLoading] = useState(true);

    // View
    const [view, setView] = useState("cards");

    // Filters
    const [search, setSearch] = useState("");
    const [filterSpecies, setFilterSpecies] = useState("all");
    const [filterSex, setFilterSex] = useState("all");
    const [filterAge, setFilterAge] = useState("all");

    // Form modal
    const [showModal, setShowModal] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState("");

    // Quick panel
    const [selectedPet, setSelectedPet] = useState(null);
    const [panelRecords, setPanelRecords] = useState([]);
    const [panelAppts, setPanelAppts] = useState([]);
    const [panelLoading, setPanelLoading] = useState(false);

    useEffect(() => {
        if (token) loadAll();
    }, [token]);

    const loadAll = async () => {
        try {
            const { start, end } = getWeekRange();
            const [petsData, apptsData] = await Promise.all([
                getPets(token),
                getAppointments(token).catch(() => []),
            ]);
            setPets(petsData);
            const allAppts = Array.isArray(apptsData) ? apptsData : (apptsData.results || []);
            setWeekAppts(allAppts.filter(a => {
                const d = new Date(a.date);
                return d >= start && d <= end;
            }));
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    // ─── Metrics ──────────────────────────────────────────────
    const totalCaninos = pets.filter(isCanino).length;
    const totalFelinos = pets.filter(isFelino).length;

    // Distinct pets with appointment this week
    const petIdsThisWeek = new Set(
        weekAppts
            .map(a => a.pet_id ?? a.pet?.id ?? (typeof a.pet === "number" ? a.pet : null))
            .filter(Boolean)
    );
    const petsWithApptCount = petIdsThisWeek.size || weekAppts.length;

    // Pets registered this month (if created_at available)
    const now = new Date();
    const petsThisMonth = pets.filter(p => {
        if (!p.created_at) return false;
        const d = new Date(p.created_at);
        return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    }).length;

    // ─── Filters ──────────────────────────────────────────────
    const filtered = pets.filter(p => {
        const q = search.toLowerCase();
        const matchSearch = !q ||
            p.name.toLowerCase().includes(q) ||
            p.species.toLowerCase().includes(q) ||
            (p.breed || "").toLowerCase().includes(q) ||
            (p.owner?.name || "").toLowerCase().includes(q);

        const matchSpecies = filterSpecies === "all" ||
            (filterSpecies === "caninos" && isCanino(p)) ||
            (filterSpecies === "felinos" && isFelino(p));

        const matchSex = filterSex === "all" || p.sex === filterSex;
        const matchAge = filterAge === "all" || getAgeGroup(p.birth_date) === filterAge;

        return matchSearch && matchSpecies && matchSex && matchAge;
    });

    const hasActiveFilters = search || filterSpecies !== "all" || filterSex !== "all" || filterAge !== "all";

    // ─── Panel ────────────────────────────────────────────────
    const openPanel = async (pet) => {
        setSelectedPet(pet);
        setPanelLoading(true);
        setPanelRecords([]);
        setPanelAppts([]);
        try {
            const [records, appts] = await Promise.all([
                getMedicalRecords(token, { pet: pet.id }),
                getAppointments(token, { pet: pet.id }).catch(() => []),
            ]);
            setPanelRecords(Array.isArray(records) ? records : (records.results || []));
            setPanelAppts(Array.isArray(appts) ? appts : (appts.results || []));
        } catch (err) {
            console.log(err);
        } finally {
            setPanelLoading(false);
        }
    };

    const closePanel = () => {
        setSelectedPet(null);
        setPanelRecords([]);
        setPanelAppts([]);
    };

    // ─── CRUD ─────────────────────────────────────────────────
    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError("");
        if (!form.name.trim()) { setFormError("El nombre es obligatorio"); return; }
        if (!form.species.trim()) { setFormError("La especie es obligatoria"); return; }
        if (!form.owner.name.trim()) { setFormError("El nombre del propietario es obligatorio"); return; }
        const payload = { ...form, birth_date: form.birth_date || null };
        try {
            if (editing) {
                await updatePet(token, editing.id, payload);
            } else {
                await createPet(token, payload);
            }
            setForm(EMPTY_FORM);
            setEditing(null);
            setShowModal(false);
            loadAll();
        } catch (err) {
            setFormError(err.response?.data?.detail || "Error al guardar mascota");
        }
    };

    const handleEdit = (pet) => {
        setEditing(pet);
        setForm({
            name: pet.name,
            species: pet.species,
            breed: pet.breed || "",
            birth_date: pet.birth_date || "",
            sex: pet.sex || "unknown",
            color: pet.color || "",
            owner: { name: pet.owner?.name || "", phone: pet.owner?.phone || "" },
        });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        if (!confirm("¿Eliminar esta mascota? También se eliminará su historial.")) return;
        try {
            await deletePet(token, id);
            if (selectedPet?.id === id) closePanel();
            loadAll();
        } catch (err) {
            alert("Error al eliminar");
        }
    };

    const handleClose = () => {
        setShowModal(false);
        setEditing(null);
        setForm(EMPTY_FORM);
        setFormError("");
    };

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    return (
        <div>
            {/* Page header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Mascotas</h1>
                    <p className="page-subtitle">{pets.length} registrada{pets.length !== 1 ? "s" : ""}</p>
                </div>
                <button
                    className="btn btn-primary btn-md"
                    onClick={() => { setEditing(null); setForm(EMPTY_FORM); setFormError(""); setShowModal(true); }}
                >
                    + Nueva Mascota
                </button>
            </div>

            {/* Metrics */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px", marginBottom: "24px" }}>
                {/* Total */}
                <div className="stat-card" style={{ borderTop: "3px solid var(--c-primary)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                        <p className="stat-label">Total mascotas</p>
                        <div style={iconBox("var(--c-primary-light)")}>
                            <Ic.Paw s={16} c="var(--c-primary-dark)" />
                        </div>
                    </div>
                    <p className="stat-value" style={{ color: "var(--c-primary-dark)" }}>{pets.length}</p>
                    {petsThisMonth > 0 ? (
                        <p className="stat-sub" style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--c-success-text)" }}>
                            <Ic.TrendUp s={12} c="var(--c-success-text)" />
                            +{petsThisMonth} este mes
                        </p>
                    ) : (
                        <p className="stat-sub">registradas en total</p>
                    )}
                </div>

                {/* Caninos */}
                <div className="stat-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                        <p className="stat-label">Caninos</p>
                        <div style={iconBox("#dbeafe")}>
                            <Ic.Dog s={16} c="#3b82f6" />
                        </div>
                    </div>
                    <p className="stat-value" style={{ color: "#1d4ed8" }}>{totalCaninos}</p>
                    <p className="stat-sub">
                        {pets.length > 0 ? Math.round(totalCaninos / pets.length * 100) : 0}% del total
                    </p>
                </div>

                {/* Felinos */}
                <div className="stat-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                        <p className="stat-label">Felinos</p>
                        <div style={iconBox("#fce7f3")}>
                            <Ic.Cat s={16} c="#ec4899" />
                        </div>
                    </div>
                    <p className="stat-value" style={{ color: "#be185d" }}>{totalFelinos}</p>
                    <p className="stat-sub">
                        {pets.length > 0 ? Math.round(totalFelinos / pets.length * 100) : 0}% del total
                    </p>
                </div>

                {/* Citas esta semana */}
                <div className="stat-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                        <p className="stat-label">Citas esta semana</p>
                        <div style={iconBox("var(--c-warning-bg)")}>
                            <Ic.Calendar s={16} c="var(--c-warning-text)" />
                        </div>
                    </div>
                    <p className="stat-value" style={{ color: "var(--c-warning-text)" }}>{petsWithApptCount}</p>
                    <p className="stat-sub">
                        {weekAppts.length} cita{weekAppts.length !== 1 ? "s" : ""} programada{weekAppts.length !== 1 ? "s" : ""}
                    </p>
                </div>
            </div>

            {/* Filter bar */}
            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginBottom: "16px" }}>
                {/* Search */}
                <div style={{ position: "relative", flex: "1 1 220px", maxWidth: "300px" }}>
                    <div style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                        <Ic.Search s={14} c="var(--c-text-3)" />
                    </div>
                    <input
                        type="text"
                        className="input"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Nombre, raza, especie, dueño..."
                        style={{ paddingLeft: "32px" }}
                    />
                </div>

                {/* Species chips */}
                <div style={{ display: "flex", gap: "3px", background: "var(--c-subtle)", padding: "3px", borderRadius: "var(--r-md)", border: "1px solid var(--c-border)" }}>
                    {[
                        { key: "all", label: "Todos" },
                        { key: "caninos", label: "Caninos", icon: <Ic.Dog s={13} /> },
                        { key: "felinos", label: "Felinos", icon: <Ic.Cat s={13} /> },
                    ].map(({ key, label, icon }) => (
                        <button
                            key={key}
                            onClick={() => setFilterSpecies(key)}
                            style={{
                                display: "inline-flex", alignItems: "center", gap: "5px",
                                height: "28px", padding: "0 10px",
                                borderRadius: "var(--r-sm)", border: "none", cursor: "pointer",
                                fontSize: "12.5px", fontWeight: "600", fontFamily: "inherit",
                                background: filterSpecies === key ? "var(--c-surface)" : "transparent",
                                color: filterSpecies === key ? "var(--c-text)" : "var(--c-text-2)",
                                boxShadow: filterSpecies === key ? "var(--shadow-xs)" : "none",
                                transition: "all var(--t)",
                            }}
                        >
                            {icon}
                            {label}
                        </button>
                    ))}
                </div>

                {/* Sex select */}
                <select
                    className="select-input"
                    value={filterSex}
                    onChange={e => setFilterSex(e.target.value)}
                    style={{ width: "auto", height: "36px", fontSize: "13px" }}
                >
                    <option value="all">Todos los sexos</option>
                    <option value="male">Macho</option>
                    <option value="female">Hembra</option>
                    <option value="unknown">Sin especificar</option>
                </select>

                {/* Age select */}
                <select
                    className="select-input"
                    value={filterAge}
                    onChange={e => setFilterAge(e.target.value)}
                    style={{ width: "auto", height: "36px", fontSize: "13px" }}
                >
                    <option value="all">Todas las edades</option>
                    <option value="cachorro">Cachorro (&lt;1 año)</option>
                    <option value="joven">Joven (1–3 años)</option>
                    <option value="adulto">Adulto (3–8 años)</option>
                    <option value="senior">Senior (&gt;8 años)</option>
                </select>

                {/* Clear */}
                {hasActiveFilters && (
                    <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => { setSearch(""); setFilterSpecies("all"); setFilterSex("all"); setFilterAge("all"); }}
                    >
                        <Ic.X s={12} />
                        Limpiar
                    </button>
                )}

                <div style={{ flex: 1 }} />

                {/* View toggle */}
                <div style={{ display: "flex", gap: "3px", background: "var(--c-subtle)", padding: "3px", borderRadius: "var(--r-md)", border: "1px solid var(--c-border)" }}>
                    {[{ key: "cards", I: Ic.Grid }, { key: "table", I: Ic.Rows }].map(({ key, I }) => (
                        <button
                            key={key}
                            onClick={() => setView(key)}
                            style={{
                                width: "30px", height: "28px",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                borderRadius: "var(--r-sm)", border: "none", cursor: "pointer",
                                background: view === key ? "var(--c-surface)" : "transparent",
                                color: view === key ? "var(--c-text)" : "var(--c-text-3)",
                                boxShadow: view === key ? "var(--shadow-xs)" : "none",
                                transition: "all var(--t)",
                            }}
                        >
                            <I s={15} />
                        </button>
                    ))}
                </div>
            </div>

            {/* Results count */}
            {hasActiveFilters && (
                <p style={{ fontSize: "12.5px", color: "var(--c-text-3)", marginBottom: "12px" }}>
                    {filtered.length} resultado{filtered.length !== 1 ? "s" : ""} de {pets.length} mascotas
                </p>
            )}

            {/* Empty state */}
            {filtered.length === 0 && (
                <div className="empty-state">
                    {hasActiveFilters ? (
                        <p className="empty-state-title">No se encontraron mascotas con esos filtros</p>
                    ) : (
                        <>
                            <p className="empty-state-title">Aún no hay mascotas registradas</p>
                            <p className="empty-state-sub">Usa el botón "Nueva Mascota" para comenzar</p>
                        </>
                    )}
                </div>
            )}

            {/* Cards view */}
            {view === "cards" && filtered.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(272px, 1fr))", gap: "14px" }}>
                    {filtered.map(pet => (
                        <PetCard
                            key={pet.id}
                            pet={pet}
                            onSelect={() => openPanel(pet)}
                            onEdit={handleEdit}
                            onDelete={handleDelete}
                        />
                    ))}
                </div>
            )}

            {/* Table view */}
            {view === "table" && filtered.length > 0 && (
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Mascota</th>
                                <th>Especie / Raza</th>
                                <th>Propietario</th>
                                <th>Edad · Sexo</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((pet) => {
                                const accent = speciesAccent(pet);
                                return (
                                    <tr key={pet.id} style={{ cursor: "pointer" }} onClick={() => openPanel(pet)}>
                                        <td>
                                            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                                <div style={{
                                                    width: "34px", height: "34px", borderRadius: "8px", flexShrink: 0,
                                                    background: accent.bg, border: `1px solid ${accent.border}`,
                                                    display: "flex", alignItems: "center", justifyContent: "center",
                                                }}>
                                                    <SpeciesIcon pet={pet} size={17} color={accent.icon} />
                                                </div>
                                                <div>
                                                    <span style={{ fontWeight: "600" }}>{pet.name}</span>
                                                    {pet.color && <span style={{ display: "block", fontSize: "12px", color: "var(--c-text-3)" }}>{pet.color}</span>}
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            {pet.species}
                                            {pet.breed && <span style={{ color: "var(--c-text-3)" }}> · {pet.breed}</span>}
                                        </td>
                                        <td>
                                            <span>{pet.owner?.name || "—"}</span>
                                            {pet.owner?.phone && <span style={{ display: "block", fontSize: "12px", color: "var(--c-text-3)" }}>{pet.owner.phone}</span>}
                                        </td>
                                        <td style={{ color: "var(--c-text-2)" }}>
                                            {calcAge(pet.birth_date) || "—"}
                                            {pet.sex && pet.sex !== "unknown" && (
                                                <span style={{ color: "var(--c-text-3)" }}> · {SEX_LABELS[pet.sex]}</span>
                                            )}
                                        </td>
                                        <td onClick={e => e.stopPropagation()}>
                                            <div style={{ display: "flex", gap: "6px" }}>
                                                <button className="btn btn-secondary btn-sm" onClick={() => handleEdit(pet)}>
                                                    <Ic.Edit s={13} /> Editar
                                                </button>
                                                <button className="btn btn-danger btn-sm" onClick={() => handleDelete(pet.id)}>
                                                    <Ic.Trash s={13} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    <div className="table-footer">
                        {filtered.length} mascota{filtered.length !== 1 ? "s" : ""}
                        {hasActiveFilters && ` de ${pets.length} total`}
                    </div>
                </div>
            )}

            {/* Quick profile panel */}
            {selectedPet && (
                <QuickPanel
                    pet={selectedPet}
                    records={panelRecords}
                    appointments={panelAppts}
                    loading={panelLoading}
                    onClose={closePanel}
                    onEdit={handleEdit}
                    navigate={navigate}
                />
            )}

            {/* Form modal */}
            {showModal && (
                <PetModal
                    form={form}
                    setForm={setForm}
                    editing={editing}
                    onSubmit={handleSubmit}
                    onClose={handleClose}
                    error={formError}
                />
            )}
        </div>
    );
};

// Small icon box helper
const iconBox = (bg) => ({
    width: "32px", height: "32px", borderRadius: "8px",
    background: bg, display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0,
});

export default Pets;
