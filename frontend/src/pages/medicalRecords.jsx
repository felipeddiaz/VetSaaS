import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { apiError } from "../utils/apiError";
import { useConfirm } from "../components/ConfirmDialog";
import {
    getMedicalRecords, createMedicalRecord, updateMedicalRecord,
    deleteMedicalRecord, getMedicalRecord, closeMedicalRecord,
} from "../api/medicalRecords";
import { createPrescription, downloadPrescriptionPDF } from "../api/prescriptions";
import { getPets } from "../api/pets";
import { getProducts, addMedicalRecordProduct, removeMedicalRecordProduct } from "../api/inventory";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import { toast } from "sonner";
import PrescriptionForm from "../components/prescriptions/PrescriptionForm";
import SearchSelect from "../components/SearchSelect";
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
    const [searchParams] = useSearchParams();

    const [records,       setRecords]       = useState([]);
    const [pets,          setPets]          = useState([]);
    const [isLoadingPets, setIsLoadingPets] = useState(true);
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
    const [showPrescriptionModal, setShowPrescriptionModal] = useState(false);
    const [prescriptionTarget, setPrescriptionTarget] = useState(null);
    const [form,            setForm]            = useState(EMPTY_FORM);
    const [downloadingPrescriptionId, setDownloadingPrescriptionId] = useState(null);

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
        setIsLoadingPets(true);
        try {
            const petsData = await getPets();
            setPets(normalizeList(petsData));
        } catch { setPets([]); }
        finally { setIsLoadingPets(false); }

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
            p.owner_name?.toLowerCase().includes(q)
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
        e.preventDefault();
        if (!form.pet)              { toast.error("Selecciona una mascota"); return; }
        if (!form.diagnosis.trim()) { toast.error("El diagnóstico es obligatorio"); return; }
        if (!form.treatment.trim()) { toast.error("El tratamiento es obligatorio"); return; }
        try {
            const payload = {
                pet: form.pet, diagnosis: form.diagnosis, treatment: form.treatment,
                notes: form.notes, weight: form.weight || null, appointment: form.appointment || null,
            };
            if (editing) {
                const p = updateMedicalRecord(token, editing.id, payload)
                    .then(async () => setSavedRecord(await getMedicalRecord(token, editing.id)));
                await toast.promise(p, {
                    loading: 'Actualizando...',
                    success: 'Consulta actualizada',
                    error: (err) => apiError(err, "Error al guardar"),
                });
            } else {
                const p = createMedicalRecord(token, payload).then(async (result) => {
                    setSavedRecord(await getMedicalRecord(token, result.id));
                    setPetCounts(prev => ({ ...prev, [form.pet]: (prev[form.pet] || 0) + 1 }));
                });
                await toast.promise(p, {
                    loading: 'Registrando...',
                    success: 'Consulta registrada. Ahora puedes agregar productos utilizados.',
                    error: (err) => apiError(err, "Error al guardar"),
                });
            }
            loadRecords();
        } catch (err) { }
    };

    const handleAddProduct = async () => {
        if (!savedRecord?.can_modify_charges) { toast.error("No puedes modificar esta consulta"); return; }
        if (savedRecord?.status === "closed") { toast.error("La consulta está cerrada"); return; }
        if (!productLine.product)                              { toast.error("Selecciona un producto"); return; }
        if (!productLine.quantity || Number(productLine.quantity) <= 0) { toast.error("La cantidad debe ser mayor a 0"); return; }
        const selected = productMap[productLine.product];
        if (!selected?.presentation?.id) { toast.error("El producto seleccionado no tiene presentación configurada"); return; }
        try {
            const p = addMedicalRecordProduct(savedRecord.id, { presentation: selected.presentation.id, quantity: productLine.quantity })
                .then(async () => {
                    setSavedRecord(await getMedicalRecord(token, savedRecord.id));
                    setProductLine({ product: "", quantity: "1" });
                });
            await toast.promise(p, {
                loading: 'Agregando...',
                success: 'Producto agregado',
                error: (err) => apiError(err, "Error al agregar producto"),
            });
        } catch (err) {}
    };

    const handleRemoveProduct = async (id) => {
        if (!savedRecord?.can_modify_charges) { toast.error("No puedes modificar esta consulta"); return; }
        if (savedRecord?.status === "closed") { toast.error("La consulta está cerrada"); return; }
        try {
            const p = removeMedicalRecordProduct(savedRecord.id, id)
                .then(async () => setSavedRecord(await getMedicalRecord(token, savedRecord.id)));
            await toast.promise(p, {
                loading: 'Quitando...',
                success: 'Producto removido',
                error: (err) => apiError(err, "Error al quitar producto"),
            });
        } catch (err) {}
    };

    const handleCloseRecord = async (record) => {
        if (!record?.can_close) {
            toast.error("No puedes finalizar esta consulta");
            return;
        }
        const ok = await confirm({
            title: "Finalizar consulta",
            message: "La consulta quedará cerrada y no podrás modificar productos o servicios.",
            confirmText: "Finalizar",
            dangerMode: false,
        });
        if (!ok) return;

        try {
            const p = closeMedicalRecord(token, record.id).then(async () => {
                await loadRecords();
                if (savedRecord?.id === record.id) {
                    setSavedRecord(await getMedicalRecord(token, savedRecord.id));
                }
            });
            await toast.promise(p, {
                loading: 'Finalizando...',
                success: 'Consulta finalizada',
                error: (err) => apiError(err, "No se pudo finalizar la consulta")
            });
        } catch (err) {}
    };

    const replaceRecordInState = (updatedRecord) => {
        setRecords(prev => prev.map(record => record.id === updatedRecord.id ? { ...record, ...updatedRecord } : record));
        if (savedRecord?.id === updatedRecord.id) {
            setSavedRecord(updatedRecord);
        }
    };

    const openPrescriptionModal = (record) => {
        if (!record || record.prescription_id) return;
        if (record.status === "closed") {
            toast.error("No puedes crear una receta en una consulta cerrada");
            return;
        }
        setPrescriptionTarget(record);
        setShowPrescriptionModal(true);
    };

    const closePrescriptionModal = () => {
        setShowPrescriptionModal(false);
        setPrescriptionTarget(null);
    };

    const handlePrescriptionSubmit = async (payload) => {
        try {
            const p = createPrescription(payload).then(async () => {
                const refreshed = await getMedicalRecord(token, payload.medical_record);
                replaceRecordInState(refreshed);
                closePrescriptionModal();
            });
            await toast.promise(p, { loading: 'Creando receta...', success: 'Receta creada', error: 'Error al crear receta' });
        } catch (err) {}
    };

    const handleDownloadPrescription = async (prescriptionId) => {
        setDownloadingPrescriptionId(prescriptionId);
        try {
            const blob = await downloadPrescriptionPDF(prescriptionId);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `receta_${prescriptionId}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            toast.error(apiError(err, "No se pudo descargar la receta"));
        } finally {
            setDownloadingPrescriptionId(null);
        }
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
            const p = deleteMedicalRecord(token, id).then(() => loadRecords());
            await toast.promise(p, { loading: 'Eliminando...', success: 'Consulta eliminada', error: 'Error al eliminar' });
        } catch {}
    };

    const closeModal = () => {
        setShowModal(false); setEditing(null); setSavedRecord(null);
        setProductLine({ product: "", quantity: "1" });
        setForm(EMPTY_FORM);
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

            {/* ── Main two-column layout ───────────────────────────────────── */}
            <div className={styles.pageLayout}>

                {/* ══ LEFT: Pet sidebar ══════════════════════════════════════ */}
                <aside className={styles.petSidebar}>
                    <div className={styles.sidebarHeader}>Mascotas</div>

                    <div className={styles.sidebarSearchWrap}>
                        <span className={styles.sidebarSearchIcon}><Icon.Search /></span>
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
                                                                                {record.status === "closed" && (
                                                                                    <span className="badge badge-default">Cerrada</span>
                                                                                )}
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
                                                                                    {record.status !== "closed" && (
                                                                                        <button className="btn btn-secondary btn-sm"
                                                                                            onClick={() => handleEdit(record)}>Editar</button>
                                                                                    )}
                                                                                    {record.can_close && record.status !== "closed" && (
                                                                                        <button className="btn btn-primary btn-sm"
                                                                                            onClick={() => handleCloseRecord(record)}>
                                                                                            Finalizar consulta
                                                                                        </button>
                                                                                    )}
                                                                                    {record.status !== "closed" && (
                                                                                        <button className="btn btn-danger btn-sm"
                                                                                            onClick={() => handleDelete(record.id)}>Eliminar</button>
                                                                                    )}
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
                                                                                        : record.status === "closed"
                                                                                            ? <span className="badge badge-default">Consulta cerrada: no admite receta nueva</span>
                                                                                            : canCreate && (
                                                                                            <button className="btn btn-purple btn-sm"
                                                                                                onClick={() => openPrescriptionModal(record)}>
                                                                                                Crear Receta
                                                                                            </button>
                                                                                        )
                                                                                    }
                                                                                    {record.invoice_id && (
                                                                                        <span className="badge badge-info">Factura generada ✓</span>
                                                                                    )}
                                                                                </div>
                                                                                {record.prescription_summary && (
                                                                                    <div className={styles.expandedSection}>
                                                                                        <div className={styles.expandedLabel}>Receta médica</div>
                                                                                        <div className="card" style={{ padding: "12px", background: "var(--c-purple-bg)", borderColor: "#ddd6fe" }}>
                                                                                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                                                                                                <span style={{ fontSize: "12px", color: "var(--c-text-2)" }}>
                                                                                                    {record.prescription_summary.items.length} medicamento{record.prescription_summary.items.length !== 1 ? "s" : ""}
                                                                                                </span>
                                                                                                <button
                                                                                                    className="btn btn-purple btn-xs"
                                                                                                    onClick={() => handleDownloadPrescription(record.prescription_summary.id)}
                                                                                                    disabled={downloadingPrescriptionId === record.prescription_summary.id}
                                                                                                >
                                                                                                    {downloadingPrescriptionId === record.prescription_summary.id ? "..." : "PDF"}
                                                                                                </button>
                                                                                            </div>
                                                                                            <div style={{ display: "grid", gap: "8px" }}>
                                                                                                {record.prescription_summary.items.map(item => (
                                                                                                    <div key={item.id} style={{ background: "white", border: "1px solid #ddd6fe", borderRadius: "8px", padding: "10px" }}>
                                                                                                        <div style={{ fontWeight: "600", fontSize: "13px", marginBottom: "4px" }}>
                                                                                                            {item.product_name} · {item.quantity} {item.product_unit}
                                                                                                        </div>
                                                                                                        <div style={{ fontSize: "12px", color: "var(--c-text-2)" }}>
                                                                                                            Dosis: {item.dose}
                                                                                                            {item.duration ? ` · Duración: ${item.duration}` : ""}
                                                                                                        </div>
                                                                                                        {item.instructions && (
                                                                                                            <div style={{ fontSize: "12px", color: "var(--c-text-2)", marginTop: "4px" }}>
                                                                                                                {item.instructions}
                                                                                                            </div>
                                                                                                        )}
                                                                                                    </div>
                                                                                                ))}
                                                                                            </div>
                                                                                            {record.prescription_summary.notes && (
                                                                                                <p style={{ fontSize: "12px", color: "var(--c-text-2)", marginTop: "10px", marginBottom: 0 }}>
                                                                                                    Nota: {record.prescription_summary.notes}
                                                                                                </p>
                                                                                            )}
                                                                                        </div>
                                                                                    </div>
                                                                                )}
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
                                    <div className="form-group">
                                        <label className="form-label" htmlFor="medical-record-pet">MASCOTA *</label>
                                        <SearchSelect
                                            id="medical-record-pet"
                                            name="medical-record-pet"
                                            value={form.pet ? { id: form.pet, label: pets.find(p => String(p.id) === String(form.pet))?.name ?? "" } : null}
                                            onChange={item => setForm({ ...form, pet: item?.id ?? "" })}
                                            onSearch={q => {
                                                const low = q.toLowerCase();
                                                const filtered = pets.filter(p => p.name.toLowerCase().includes(low));
                                                return Promise.resolve(filtered.map(p => ({ id: p.id, label: p.name })));
                                            }}
                                            placeholder={isLoadingPets ? "Cargando mascotas..." : "Buscar mascota..."}
                                            disabled={isLoadingPets}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" htmlFor="medical-record-weight">PESO (kg)</label>
                                        <input id="medical-record-weight" name="medical-record-weight" type="number" step="0.01" className="input" value={form.weight}
                                            onChange={e => setForm({ ...form, weight: e.target.value })} placeholder="Ej: 5.5" />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" htmlFor="medical-record-diagnosis">DIAGNÓSTICO *</label>
                                        <textarea id="medical-record-diagnosis" name="medical-record-diagnosis" className="textarea-input" value={form.diagnosis}
                                            onChange={e => setForm({ ...form, diagnosis: e.target.value })}
                                            placeholder="Describe el diagnóstico..." />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" htmlFor="medical-record-treatment">TRATAMIENTO *</label>
                                        <textarea id="medical-record-treatment" name="medical-record-treatment" className="textarea-input" value={form.treatment}
                                            onChange={e => setForm({ ...form, treatment: e.target.value })}
                                            placeholder="Describe el tratamiento..." />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" htmlFor="medical-record-notes">NOTAS</label>
                                        <textarea id="medical-record-notes" name="medical-record-notes" className="textarea-input" style={{ minHeight: "60px" }}
                                            value={form.notes}
                                            onChange={e => setForm({ ...form, notes: e.target.value })}
                                            placeholder="Notas adicionales..." />
                                    </div>
                                </form>
                            ) : (
                                <div>
                                    <div style={{ marginBottom: "18px" }}>
                                        <p style={{ fontWeight: "600", fontSize: "13px", marginBottom: "6px" }}>Medicamentos recetados</p>
                                        <p style={{ color: "var(--c-text-3)", fontSize: "12px", marginBottom: "10px" }}>
                                            Esto corresponde a lo que el paciente debe llevar o administrar despues de la consulta.
                                        </p>
                                        {savedRecord.prescription_summary ? (
                                            <div className="card" style={{ padding: "12px", background: "var(--c-purple-bg)", borderColor: "#ddd6fe" }}>
                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                                                    <span style={{ fontSize: "12px", color: "var(--c-text-2)" }}>
                                                        {savedRecord.prescription_summary.items.length} medicamento{savedRecord.prescription_summary.items.length !== 1 ? "s" : ""}
                                                    </span>
                                                    <button
                                                        className="btn btn-purple btn-xs"
                                                        onClick={() => handleDownloadPrescription(savedRecord.prescription_summary.id)}
                                                        disabled={downloadingPrescriptionId === savedRecord.prescription_summary.id}
                                                    >
                                                        {downloadingPrescriptionId === savedRecord.prescription_summary.id ? "Descargando..." : "Descargar PDF"}
                                                    </button>
                                                </div>
                                                {savedRecord.prescription_summary.items.map(item => (
                                                    <div key={item.id} style={{ background: "white", border: "1px solid #ddd6fe", borderRadius: "8px", padding: "10px", marginBottom: "8px" }}>
                                                        <div style={{ fontWeight: "600", fontSize: "13px", marginBottom: "4px" }}>
                                                            {item.product_name} · {item.quantity} {item.product_unit}
                                                        </div>
                                                        <div style={{ fontSize: "12px", color: "var(--c-text-2)" }}>
                                                            Dosis: {item.dose}
                                                            {item.duration ? ` · Duración: ${item.duration}` : ""}
                                                        </div>
                                                        {item.instructions && (
                                                            <div style={{ fontSize: "12px", color: "var(--c-text-2)", marginTop: "4px" }}>
                                                                {item.instructions}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                                {savedRecord.prescription_summary.notes && (
                                                    <p style={{ fontSize: "12px", color: "var(--c-text-2)", marginTop: "8px", marginBottom: 0 }}>
                                                        Nota: {savedRecord.prescription_summary.notes}
                                                    </p>
                                                )}
                                            </div>
                                        ) : (
                                            <>
                                                {!savedRecord.prescription_id && savedRecord.status !== "closed" && canCreate && (
                                                    <div style={{ marginBottom: "14px" }}>
                                                        <button className="btn btn-purple btn-sm" onClick={() => openPrescriptionModal(savedRecord)}>
                                                            Crear Receta
                                                        </button>
                                                    </div>
                                                )}
                                                {savedRecord.status === "closed" && !savedRecord.prescription_id && (
                                                    <p style={{ color: "var(--c-text-3)", fontSize: "12px", marginBottom: "12px" }}>
                                                        La consulta ya está cerrada y no permite crear una receta nueva.
                                                    </p>
                                                )}
                                            </>
                                        )}
                                    </div>

                                    <p style={{ fontWeight: "600", fontSize: "13px", marginBottom: "6px" }}>Productos consumidos en consulta</p>
                                    <p style={{ color: "var(--c-text-3)", fontSize: "12px", marginBottom: "12px" }}>
                                        Esto descuenta stock interno de la clínica. No sustituye a la receta médica.
                                    </p>
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
                                                    <button
                                                        className="btn btn-danger btn-xs"
                                                        onClick={() => handleRemoveProduct(p.id)}
                                                        disabled={!savedRecord?.can_modify_charges || savedRecord?.status === "closed"}
                                                    >
                                                        Quitar
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p style={{ color: "var(--c-text-3)", fontSize: "13px", marginBottom: "14px" }}>Sin productos agregados aún.</p>
                                    )}
                                    <div style={{ display: "flex", gap: "8px", marginBottom: "4px" }}>
                                        <select className="select-input" style={{ flex: 2 }} value={productLine.product}
                                            disabled={!savedRecord?.can_modify_charges || savedRecord?.status === "closed"}
                                            onChange={e => setProductLine({ ...productLine, product: e.target.value })}>
                                            <option value="">Seleccionar producto</option>
                                            {products.map(p => {
                                                const pres = p.presentation || {};
                                                return <option key={p.id} value={p.id}>{p.name} (stock: {parseFloat(pres.stock ?? 0) || 0} {pres.base_unit_display || pres.base_unit || ""})</option>;
                                            })}
                                        </select>
                                        <input type="number" step="0.01" min="0.01" className="input" style={{ flex: 1 }}
                                            disabled={!savedRecord?.can_modify_charges || savedRecord?.status === "closed"}
                                            value={productLine.quantity}
                                            onChange={e => setProductLine({ ...productLine, quantity: e.target.value })}
                                            placeholder="Cant." />
                                        <button
                                            className="btn btn-primary btn-md"
                                            onClick={handleAddProduct}
                                            disabled={!savedRecord?.can_modify_charges || savedRecord?.status === "closed"}
                                        >
                                            + Agregar
                                        </button>
                                    </div>
                                    {savedRecord?.status === "closed" && (
                                        <p style={{ color: "var(--c-text-3)", fontSize: "12px", marginTop: "8px" }}>
                                            Esta consulta está cerrada.
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                        <div className="modal-footer">
                            {!savedRecord ? (
                                <>
                                    <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleSubmit}>
                                        Guardar consulta
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

            {showPrescriptionModal && prescriptionTarget && (
                <PrescriptionForm
                    title="Nueva Receta"
                    initialValue={{ pet: prescriptionTarget.pet, medical_record: prescriptionTarget.id, notes: "", items: [] }}
                    pets={pets}
                    products={products}
                    medicalRecordsForPet={[prescriptionTarget]}
                    lockedPet={true}
                    lockedMedicalRecord={true}
                    submitLabel="Crear Receta"
                    onSubmit={handlePrescriptionSubmit}
                    onCancel={closePrescriptionModal}
                />
            )}
        </div>
    );
};

export default MedicalRecords;
