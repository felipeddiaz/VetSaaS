import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { apiError } from "../utils/apiError";
import { useConfirm } from "../components/ConfirmDialog";
import {
    getMedicalRecords, createMedicalRecord, updateMedicalRecord,
    deleteMedicalRecord, getMedicalRecord,
} from "../api/medicalRecords";
import { getPets } from "../api/pets";
import { getProducts, addMedicalRecordProduct, removeMedicalRecordProduct } from "../api/inventory";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import styles from "./medicalRecords.module.css";

const EMPTY_FORM = { pet: "", diagnosis: "", treatment: "", notes: "", weight: "", appointment: null };

const TYPE_FILTERS = [
    { id: "all",      label: "Todos" },
    { id: "general",  label: "General" },
    { id: "vacuna",   label: "Vacuna" },
    { id: "cirugia",  label: "Cirugía" },
    { id: "urgencia", label: "Urgencia" },
];

const TYPE_META = {
    general:  { color: "#10b981", bg: "rgba(16,185,129,.08)",  label: "General"  },
    vacuna:   { color: "#f59e0b", bg: "rgba(245,158,11,.08)",  label: "Vacuna"   },
    urgencia: { color: "#ef4444", bg: "rgba(239,68,68,.08)",   label: "Urgencia" },
    cirugia:  { color: "#8b5cf6", bg: "rgba(139,92,246,.08)",  label: "Cirugía"  },
};

/* ── Species helpers ──────────────────────────────────────────────────── */
const SPECIES_DOG = /perro|can[ei]|dog/i;
const SPECIES_CAT = /gato|fel[iy]|cat/i;

const getSpeciesBg = (species) => {
    if (SPECIES_DOG.test(species)) return "var(--c-primary-light)";
    if (SPECIES_CAT.test(species)) return "var(--c-purple-bg)";
    return "var(--c-subtle)";
};

/* ── Record type helper ───────────────────────────────────────────────── */
const getRecordType = (record) => {
    const text = `${record.diagnosis} ${record.treatment} ${record.notes || ""}`;
    if (/urgencia|emergencia/i.test(text))          return "urgencia";
    if (/cirug|operaci|quir[úu]rg/i.test(text))    return "cirugia";
    if (/vacun/i.test(text))                         return "vacuna";
    return "general";
};

/* ── Group records by year → month ───────────────────────────────────── */
const groupByYearMonth = (records) => {
    const groups = {};
    records.forEach(record => {
        const d = new Date(record.created_at);
        const year = d.getFullYear();
        const monthRaw = d.toLocaleDateString("es-ES", { month: "long" });
        const month = monthRaw.charAt(0).toUpperCase() + monthRaw.slice(1);
        if (!groups[year]) groups[year] = {};
        if (!groups[year][month]) groups[year][month] = [];
        groups[year][month].push(record);
    });
    return Object.keys(groups)
        .sort((a, b) => b - a)
        .map(year => ({
            year,
            months: Object.keys(groups[year])
                .sort((a, b) => {
                    const aD = new Date(groups[year][a][0].created_at);
                    const bD = new Date(groups[year][b][0].created_at);
                    return bD - aD;
                })
                .map(month => ({ month, records: groups[year][month] })),
        }));
};

/* ─────────────────────────────────────────────────────────────────────── */

const MedicalRecords = () => {
    const { token, initializing, user } = useAuth();
    const confirm = useConfirm();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const [records,    setRecords]    = useState([]);
    const [pets,       setPets]       = useState([]);
    const [products,   setProducts]   = useState([]);
    // R7: mapa O(1) para lookup por id (evita find() en cada interacción)
    const productMap = useMemo(() => {
        const map = {};
        products.forEach(p => { map[p.id] = p; });
        return map;
    }, [products]);
    const [loading,    setLoading]    = useState(true);
    const [totalCount, setTotalCount] = useState(0);
    const [page,       setPage]       = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const [selectedPet,   setSelectedPet]   = useState("");
    const [typeFilter,    setTypeFilter]    = useState("all");
    const [petSearch,     setPetSearch]     = useState("");
    const [historySearch, setHistorySearch] = useState("");
    const [expandedId,    setExpandedId]    = useState(null);
    const [petCounts,     setPetCounts]     = useState({});

    const [showModal,       setShowModal]       = useState(false);
    const [editing,         setEditing]         = useState(null);
    const [savedRecord,     setSavedRecord]     = useState(null);
    const [productLine,     setProductLine]     = useState({ product: "", quantity: "1" });
    const [productError,    setProductError]    = useState("");
    const [form,            setForm]            = useState(EMPTY_FORM);
    const [error,           setError]           = useState("");
    const [success,         setSuccess]         = useState("");

    useEffect(() => { if (token) loadData(); }, [token]);
    useEffect(() => { if (token) loadRecords(); }, [selectedPet, page, token]);

    useEffect(() => {
        if (!selectedPet || pets.length === 0) return;
        if (!pets.some(p => String(p.id) === String(selectedPet))) setSelectedPet("");
    }, [selectedPet, pets]);

    useEffect(() => {
        const petParam         = searchParams.get("pet");
        const appointmentParam = searchParams.get("appointment");
        if (petParam) {
            setSelectedPet(petParam);
            if (appointmentParam) {
                setForm({ ...EMPTY_FORM, pet: parseInt(petParam), appointment: parseInt(appointmentParam) });
                setShowModal(true);
            }
        }
    }, [searchParams, token]);

    const normalizeList = (data) => (Array.isArray(data) ? data : (data?.results || []));

    const loadData = async () => {
        try {
            const petsData = await getPets(token);
            setPets(normalizeList(petsData));
        } catch { setPets([]); }

        try {
            const prodsData = await getProducts({ active: "true" });
            setProducts(normalizeList(prodsData));
        } catch { setProducts([]); }

        /* Preload counts per pet */
        try {
            const allData = await getMedicalRecords(token, { page_size: 9999 });
            const allList = normalizeList(allData);
            const counts = {};
            allList.forEach(r => { counts[r.pet] = (counts[r.pet] || 0) + 1; });
            setPetCounts(counts);
        } catch {}

        setLoading(false);
    };

    const loadRecords = async () => {
        try {
            const filters = { page };
            if (selectedPet) filters.pet = selectedPet;
            const data = await getMedicalRecords(token, filters);
            const list = data.results || data;
            setRecords(list);
            setTotalPages(data.total_pages || 1);
            setTotalCount(data.count ?? list.length);
        } catch {}
    };

    /* ── Filtered by type pill ──────────────────────────────────────────── */
    const filteredByType = useMemo(() => {
        if (typeFilter === "all") return records;
        return records.filter(r => getRecordType(r) === typeFilter);
    }, [records, typeFilter]);

    /* ── Filtered by history search ─────────────────────────────────────── */
    const visibleRecords = useMemo(() => {
        if (!historySearch.trim()) return filteredByType;
        const q = historySearch.toLowerCase();
        return filteredByType.filter(r =>
            r.diagnosis.toLowerCase().includes(q) ||
            r.treatment.toLowerCase().includes(q) ||
            (r.notes || "").toLowerCase().includes(q) ||
            (r.veterinarian_name || "").toLowerCase().includes(q)
        );
    }, [filteredByType, historySearch]);

    /* ── Grouped timeline ────────────────────────────────────────────────── */
    const groupedTimeline = useMemo(() => groupByYearMonth(visibleRecords), [visibleRecords]);

    /* ── Filtered pet sidebar list ───────────────────────────────────────── */
    const filteredPets = useMemo(() => {
        if (!petSearch.trim()) return pets;
        const q = petSearch.toLowerCase();
        return pets.filter(p =>
            p.name?.toLowerCase().includes(q)       ||
            p.species?.toLowerCase().includes(q)    ||
            p.breed?.toLowerCase().includes(q)      ||
            p.owner_name?.toLowerCase().includes(q) ||
            p.owner?.toLowerCase().includes(q)
        );
    }, [pets, petSearch]);

    /* ── Pet helpers ─────────────────────────────────────────────────────── */
    const getPetInfo    = (id) => pets.find(p => String(p.id) === String(id));
    const getPetSpecies = (id) => (getPetInfo(id)?.species ?? "").toLowerCase();

    const PetIcon = ({ petId, size = 18 }) => {
        const s = getPetSpecies(petId);
        if (SPECIES_DOG.test(s)) return <Icon.Dog size={size} />;
        if (SPECIES_CAT.test(s)) return <Icon.Cat size={size} />;
        return <Icon.Paw size={size} />;
    };

    /* ── CRUD ────────────────────────────────────────────────────────────── */
    const handleSubmit = async (e) => {
        e.preventDefault(); setError("");
        if (!form.pet)              { setError("Selecciona una mascota"); return; }
        if (!form.diagnosis.trim()) { setError("El diagnóstico es obligatorio"); return; }
        if (!form.treatment.trim()) { setError("El tratamiento es obligatorio"); return; }
        try {
            const payload = {
                pet: form.pet, diagnosis: form.diagnosis, treatment: form.treatment,
                notes: form.notes, weight: form.weight || null, appointment: form.appointment || null,
            };
            if (editing) {
                await updateMedicalRecord(token, editing.id, payload);
                setSuccess("Consulta actualizada");
                setSavedRecord(await getMedicalRecord(token, editing.id));
            } else {
                const result = await createMedicalRecord(token, payload);
                setSuccess("Consulta registrada. Ahora puedes agregar productos utilizados.");
                setSavedRecord(await getMedicalRecord(token, result.id));
                /* Update counts */
                setPetCounts(prev => ({ ...prev, [form.pet]: (prev[form.pet] || 0) + 1 }));
            }
            loadRecords();
        } catch (err) { setError(apiError(err, "Error al guardar")); }
    };

    const handleAddProduct = async () => {
        setProductError("");
        if (!productLine.product)                              { setProductError("Selecciona un producto"); return; }
        if (!productLine.quantity || Number(productLine.quantity) <= 0) { setProductError("La cantidad debe ser mayor a 0"); return; }
        // R8: validar presentation.id antes de enviar (error explícito, no silencioso)
        const selected = productMap[productLine.product];
        if (!selected?.presentation?.id) { setProductError("El producto seleccionado no tiene presentación configurada"); return; }
        try {
            await addMedicalRecordProduct(savedRecord.id, { presentation: selected.presentation.id, quantity: productLine.quantity });
            setSavedRecord(await getMedicalRecord(token, savedRecord.id));
            setProductLine({ product: "", quantity: "1" });
        } catch (err) { setProductError(apiError(err, "Error al agregar producto")); }
    };

    const handleRemoveProduct = async (id) => {
        try {
            await removeMedicalRecordProduct(savedRecord.id, id);
            setSavedRecord(await getMedicalRecord(token, savedRecord.id));
        } catch { setProductError("Error al quitar producto"); }
    };

    const handleEdit = (record) => {
        setEditing(record); setSavedRecord(null);
        setForm({
            pet: record.pet, diagnosis: record.diagnosis, treatment: record.treatment,
            notes: record.notes || "", weight: record.weight || "", appointment: record.appointment || null,
        });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        const ok = await confirm({
            title: "Eliminar consulta",
            message: "Se eliminará el registro clínico de esta consulta. Esta acción no se puede deshacer.",
            confirmText: "Eliminar",
            dangerMode: true,
        });
        if (!ok) return;
        try {
            await deleteMedicalRecord(token, id);
            setSuccess("Consulta eliminada");
            loadRecords();
        } catch { setError("Error al eliminar"); }
    };

    const closeModal = () => {
        setShowModal(false); setEditing(null); setSavedRecord(null);
        setProductLine({ product: "", quantity: "1" }); setProductError("");
        setError(""); setForm(EMPTY_FORM);
    };

    const formatDate     = (ds) => new Date(ds).toLocaleDateString("es-ES", { year: "numeric", month: "long",  day: "numeric" });
    const formatDateShort = (ds) => new Date(ds).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    const canCreate  = user?.role !== "ASSISTANT";
    const petInfo    = selectedPet ? getPetInfo(selectedPet) : null;
    const petSpecies = selectedPet ? getPetSpecies(selectedPet) : "";

    return (
        <div>
            {/* ── Header ──────────────────────────────────────────────────── */}
            <div className="page-header">
                <h1 className="page-title">Historial Clínico</h1>
                {canCreate && (
                    <button className="btn btn-primary btn-md"
                        onClick={() => {
                            setEditing(null); setSavedRecord(null);
                            setForm(selectedPet ? { ...EMPTY_FORM, pet: parseInt(selectedPet) } : EMPTY_FORM);
                            setShowModal(true);
                        }}>
                        + Nueva Consulta
                    </button>
                )}
            </div>

            {error   && <div className="alert alert-danger">{error}<button className="alert-close" onClick={() => setError("")}><Icon.X s={14} /></button></div>}
            {success && <div className="alert alert-success">{success}<button className="alert-close" onClick={() => setSuccess("")}><Icon.X s={14} /></button></div>}

            {/* ── Main two-column layout ───────────────────────────────────── */}
            <div className={styles.pageLayout}>

                {/* ══ LEFT: Pet sidebar ══════════════════════════════════════ */}
                <aside className={styles.petSidebar}>
                    <div className={styles.sidebarHeader}>Mascotas</div>

                    <div className={styles.sidebarSearchWrap}>
                        <span className={styles.sidebarIcon}><Icon.Search /></span>
                        <input
                            className={styles.sidebarSearchInput}
                            placeholder="Nombre, raza, especie…"
                            value={petSearch}
                            onChange={e => setPetSearch(e.target.value)}
                        />
                    </div>

                    <div className={styles.petList}>
                        {filteredPets.length === 0 ? (
                            <p className={styles.sidebarEmpty}>Sin resultados</p>
                        ) : filteredPets.map(pet => {
                            const sp = (pet.species || "").toLowerCase();
                            const isActive = String(pet.id) === String(selectedPet);
                            return (
                                <button
                                    key={pet.id}
                                    className={`${styles.petListItem}${isActive ? ` ${styles.petListItemActive}` : ""}`}
                                    onClick={() => { setSelectedPet(String(pet.id)); setPage(1); setExpandedId(null); }}>
                                    <div className={styles.petListIcon} style={{ background: getSpeciesBg(sp) }}>
                                        {SPECIES_DOG.test(sp) ? <Icon.Dog size={15} /> :
                                         SPECIES_CAT.test(sp) ? <Icon.Cat size={15} /> :
                                         <Icon.Paw size={15} />}
                                    </div>
                                    <div className={styles.petListInfo}>
                                        <div className={styles.petListName}>{pet.name}</div>
                                        <div className={styles.petListSub}>
                                            {[pet.species, pet.breed].filter(Boolean).join(" · ") || "—"}
                                        </div>
                                    </div>
                                    {petCounts[pet.id] > 0 && (
                                        <span className={styles.petListBadge}>{petCounts[pet.id]}</span>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </aside>

                {/* ══ RIGHT: Timeline content ════════════════════════════════ */}
                <main className={styles.timelineContent}>

                    {/* ── Empty: no pet selected ────────────────────────────── */}
                    {!selectedPet ? (
                        <div className={styles.emptyCenter}>
                            <div className={styles.emptyIconWrap}>
                                <Icon.Paw size={40} />
                            </div>
                            <p className={styles.emptyTitle}>Selecciona una mascota</p>
                            <p className={styles.emptySub}>
                                Elige una mascota del panel izquierdo para ver su historial clínico completo.
                            </p>
                        </div>
                    ) : (
                        <>
                            {/* Pet banner */}
                            <div className={styles.petBanner}>
                                <div className={styles.petBannerIcon} style={{ background: getSpeciesBg(petSpecies) }}>
                                    <PetIcon petId={Number(selectedPet)} size={20} />
                                </div>
                                <div className={styles.petBannerInfo}>
                                    <div className={styles.petBannerName}>{petInfo?.name ?? "—"}</div>
                                    <div className={styles.petBannerMeta}>
                                        {petInfo?.species && <span>{petInfo.species}</span>}
                                        {petInfo?.breed   && <><span className={styles.dot}/><span>{petInfo.breed}</span></>}
                                        <span className={styles.dot}/>
                                        <span>{totalCount} consulta{totalCount !== 1 ? "s" : ""}</span>
                                    </div>
                                </div>
                                <button className="btn btn-ghost btn-sm"
                                    onClick={() => { setSelectedPet(""); setTypeFilter("all"); setPage(1); setExpandedId(null); }}>
<Icon.X s={13} /> Quitar
                                </button>
                            </div>

                            {/* Filters row */}
                            <div className={styles.filtersBar}>
                                <div className={styles.pillGroup}>
                                    {TYPE_FILTERS.map(f => (
                                        <button key={f.id}
                                            className={`${styles.filterPill}${typeFilter === f.id ? ` ${styles.filterPillActive}` : ""}`}
                                            onClick={() => setTypeFilter(f.id)}>
                                            {f.label}
                                        </button>
                                    ))}
                                </div>
                                <div className={styles.historySearchWrap}>
                                    <span className={styles.historyIcon}><Icon.Search /></span>
                                    <input
                                        className={styles.historySearchInput}
                                        placeholder="Buscar en historial…"
                                        value={historySearch}
                                        onChange={e => setHistorySearch(e.target.value)}
                                    />
                                </div>
                            </div>

                            {/* Timeline or empty */}
                            {visibleRecords.length === 0 ? (
                                <div className={styles.emptyCenter} style={{ minHeight: "240px" }}>
                                    <div className={styles.emptyIconWrap}>
                                        <Icon.Paw size={32} />
                                    </div>
                                    <p className={styles.emptyTitle} style={{ fontSize: "15px" }}>
                                        {historySearch || typeFilter !== "all"
                                            ? "No hay consultas con ese filtro"
                                            : "Esta mascota no tiene historial clínico aún"}
                                    </p>
                                </div>
                            ) : (
                                <>
                                    {groupedTimeline.map(({ year, months }) => (
                                        <div key={year} className={styles.yearGroup}>
                                            <div className={styles.yearLabel}>{year}</div>
                                            {months.map(({ month, records: monthRecords }) => (
                                                <div key={month} className={styles.monthGroup}>
                                                    <div className={styles.monthLabel}>{month}</div>
                                                    <div className={styles.timeline}>
                                                        {monthRecords.map(record => {
                                                            const type     = getRecordType(record);
                                                            const meta     = TYPE_META[type];
                                                            const isOpen   = expandedId === record.id;
                                                            return (
                                                                <div key={record.id} className={styles.timelineEntry}>
                                                                    <div className={styles.timelineDot}
                                                                        style={{ background: meta.color, boxShadow: `0 0 0 3px ${meta.color}30` }} />
                                                                    <div className={styles.timelineCard}
                                                                        style={{ borderLeftColor: meta.color }}>
                                                                        {/* Card top */}
                                                                        <div className={styles.cardTop}>
                                                                            <div className={styles.cardLeft}>
                                                                                <span className={styles.typeTag}
                                                                                    style={{ color: meta.color, background: meta.bg }}>
                                                                                    {meta.label}
                                                                                </span>
                                                                                <span className={styles.cardDate}>
                                                                                    {formatDateShort(record.created_at)}
                                                                                </span>
                                                                                <span className={styles.cardVet}>
                                                                                    Dr. {record.veterinarian_name || user?.first_name || "—"}
                                                                                </span>
                                                                            </div>
                                                                            <div className={styles.cardBadges}>
                                                                                {record.weight && (
                                                                                    <span className="badge badge-default">{record.weight} kg</span>
                                                                                )}
                                                                                {record.prescription_id && (
                                                                                    <span className="badge badge-purple">Receta</span>
                                                                                )}
                                                                                {record.invoice_id && (
                                                                                    <span className="badge badge-info">Factura</span>
                                                                                )}
                                                                            </div>
                                                                        </div>

                                                                        {/* Diagnosis snippet */}
                                                                        <p className={styles.diagnosisSnippet}>
                                                                            {record.diagnosis.length > 140
                                                                                ? record.diagnosis.slice(0, 140) + "…"
                                                                                : record.diagnosis}
                                                                        </p>

                                                                        {/* Actions */}
                                                                        <div className={styles.cardActions}>
                                                                            <button
                                                                                className={`${styles.detailBtn}${isOpen ? ` ${styles.detailBtnOpen}` : ""}`}
                                                                                onClick={() => setExpandedId(isOpen ? null : record.id)}>
                                                                                {isOpen ? <><Icon.ChevronUp /> Ocultar</> : <><Icon.ChevronDown /> Ver detalle</>}
                                                                            </button>
                                                                            {canCreate && (
                                                                                <div className={styles.crudActions}>
                                                                                    <button className="btn btn-secondary btn-sm"
                                                                                        onClick={() => handleEdit(record)}>Editar</button>
                                                                                    <button className="btn btn-danger btn-sm"
                                                                                        onClick={() => handleDelete(record.id)}>Eliminar</button>
                                                                                </div>
                                                                            )}
                                                                        </div>

                                                                        {/* Expanded panel */}
                                                                        {isOpen && (
                                                                            <div className={styles.expandedPanel}
                                                                                style={{ borderTopColor: `${meta.color}30` }}>
                                                                                <div className={styles.expandedSection}>
                                                                                    <div className={styles.expandedLabel}>Diagnóstico</div>
                                                                                    <p className={styles.expandedText}>{record.diagnosis}</p>
                                                                                </div>
                                                                                <div className={styles.expandedSection}>
                                                                                    <div className={styles.expandedLabel}>Tratamiento</div>
                                                                                    <p className={styles.expandedText}>{record.treatment}</p>
                                                                                </div>
                                                                                {record.notes && (
                                                                                    <div className={styles.expandedSection}>
                                                                                        <div className={styles.expandedLabel}>Notas</div>
                                                                                        <p className={styles.expandedText}>{record.notes}</p>
                                                                                    </div>
                                                                                )}
                                                                                <div className={styles.expandedLinks}>
                                                                                    {record.prescription_id
                                                                                        ? <span className="badge badge-purple">Receta generada ✓</span>
                                                                                        : canCreate && (
                                                                                            <button className="btn btn-purple btn-sm"
                                                                                                onClick={() => navigate(`/prescriptions?medical_record=${record.id}&pet=${record.pet}`)}>
                                                                                                Crear Receta
                                                                                            </button>
                                                                                        )
                                                                                    }
                                                                                    {record.invoice_id && (
                                                                                        <span className="badge badge-info">Factura generada ✓</span>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ))}

                                    {totalPages > 1 && (
                                        <div className={styles.pagination}>
                                            <button className="btn btn-secondary btn-sm" disabled={page === 1}
                                                onClick={() => setPage(p => Math.max(1, p - 1))}>Anterior</button>
                                            <span className={styles.paginationLabel}>Página {page} de {totalPages}</span>
                                            <button className="btn btn-secondary btn-sm" disabled={page === totalPages}
                                                onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Siguiente</button>
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    )}
                </main>
            </div>

            {/* ── Modal Nueva / Editar Consulta ─────────────────────────────── */}
            {showModal && (
                <div className="modal-overlay">
                    <div className="modal modal-md">
                        <div className="modal-header">
                            <h3>{editing ? "Editar Consulta" : "Nueva Consulta"}</h3>
                            <button className="modal-close" onClick={closeModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            {!savedRecord ? (
                                <form onSubmit={handleSubmit}>
                                    {error && <div className="alert alert-danger">{error}</div>}
                                    <div className="form-group">
                                        <label className="form-label">MASCOTA *</label>
                                        <select className="select-input" value={form.pet}
                                            onChange={e => setForm({ ...form, pet: e.target.value })}>
                                            <option value="">Seleccionar mascota</option>
                                            {pets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">PESO (kg)</label>
                                        <input type="number" step="0.01" className="input" value={form.weight}
                                            onChange={e => setForm({ ...form, weight: e.target.value })} placeholder="Ej: 5.5" />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">DIAGNÓSTICO *</label>
                                        <textarea className="textarea-input" value={form.diagnosis}
                                            onChange={e => setForm({ ...form, diagnosis: e.target.value })}
                                            placeholder="Describe el diagnóstico..." />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">TRATAMIENTO *</label>
                                        <textarea className="textarea-input" value={form.treatment}
                                            onChange={e => setForm({ ...form, treatment: e.target.value })}
                                            placeholder="Describe el tratamiento..." />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">NOTAS</label>
                                        <textarea className="textarea-input" style={{ minHeight: "60px" }}
                                            value={form.notes}
                                            onChange={e => setForm({ ...form, notes: e.target.value })}
                                            placeholder="Notas adicionales..." />
                                    </div>
                                </form>
                            ) : (
                                <div>
                                    <div className="alert alert-success" style={{ marginBottom: "20px" }}>
                                        <div>
                                            <p style={{ fontWeight: "600" }}>Consulta guardada correctamente</p>
                                            <p style={{ fontSize: "12.5px" }}>
                                                {savedRecord.diagnosis.slice(0, 60)}{savedRecord.diagnosis.length > 60 ? "…" : ""}
                                            </p>
                                        </div>
                                    </div>
                                    <p style={{ fontWeight: "600", fontSize: "13px", marginBottom: "12px" }}>Productos utilizados</p>
                                    {savedRecord.products_used?.length > 0 ? (
                                        <div style={{ marginBottom: "14px" }}>
                                            {savedRecord.products_used.map(p => (
                                                <div key={p.id} style={{
                                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                                    padding: "8px 12px", background: "var(--c-subtle)",
                                                    borderRadius: "var(--r-md)", marginBottom: "6px", border: "1px solid var(--c-border)",
                                                }}>
                                                    <span style={{ fontSize: "13.5px" }}>
                                                        {p.product_name} <span style={{ color: "var(--c-text-2)" }}>&middot; {p.quantity} {p.base_unit_display || p.base_unit || ""}</span>
                                                    </span>
                                                    <button className="btn btn-danger btn-xs" onClick={() => handleRemoveProduct(p.id)}>Quitar</button>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p style={{ color: "var(--c-text-3)", fontSize: "13px", marginBottom: "14px" }}>Sin productos agregados aún.</p>
                                    )}
                                    {productError && <div className="alert alert-danger">{productError}</div>}
                                    <div style={{ display: "flex", gap: "8px", marginBottom: "4px" }}>
                                        <select className="select-input" style={{ flex: 2 }} value={productLine.product}
                                            onChange={e => setProductLine({ ...productLine, product: e.target.value })}>
                                            <option value="">Seleccionar producto</option>
                                            {products.map(p => {
                                                const pres = p.presentation || {};
                                                return <option key={p.id} value={p.id}>{p.name} (stock: {parseFloat(pres.stock ?? 0) || 0} {pres.base_unit_display || pres.base_unit || ""})</option>;
                                            })}
                                        </select>
                                        <input type="number" step="0.01" min="0.01" className="input" style={{ flex: 1 }}
                                            value={productLine.quantity}
                                            onChange={e => setProductLine({ ...productLine, quantity: e.target.value })}
                                            placeholder="Cant." />
                                        <button className="btn btn-primary btn-md" onClick={handleAddProduct}>+ Agregar</button>
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="modal-footer">
                            {!savedRecord ? (
                                <>
                                    <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleSubmit}>
                                        Guardar y agregar productos
                                    </button>
                                    <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeModal}>Cancelar</button>
                                </>
                            ) : (
                                <button className="btn btn-secondary btn-md" style={{ width: "100%" }} onClick={closeModal}>Finalizar</button>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MedicalRecords;
