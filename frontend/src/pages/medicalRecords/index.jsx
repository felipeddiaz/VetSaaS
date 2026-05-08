import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { apiError } from "../../utils/apiError";
import { useConfirm } from "../../components/ConfirmDialog";
import {
  getMedicalRecords, createMedicalRecord, getMedicalRecord,
  deleteMedicalRecord, closeMedicalRecord,
} from "../../api/medicalRecords";
import { createPrescription, downloadPrescriptionPDF } from "../../api/prescriptions";
import { getPets } from "../../api/pets";
import { getProducts } from "../../api/inventory";
import { useAuth } from "../../auth/authContext";
import { Icon } from "../../components/icons";
import { toast } from "sonner";
import PrescriptionForm from "../../components/prescriptions/PrescriptionForm";
import PetSidebar from "./PetSidebar";
import PatientHeader from "./PatientHeader";
import Timeline from "./Timeline";
import ConsultationStepperV2 from "./ConsultationStepperV2";
import styles from "./medicalRecords.module.css";
import Layout from "../../components/Layout";

const TYPE_FILTERS = [
  { id: "all",      label: "Todos" },
  { id: "general",  label: "General" },
  { id: "vaccine",   label: "Vacuna" },
  { id: "surgery",  label: "Cirugía" },
  { id: "emergency", label: "Emergencia" },
];

const TYPE_FILTER_MAP = {
  general:  "general",
  vaccine:  "vaccine",
  surgery:  "surgery",
  emergency: "emergency",
};

const normalizeList = (data) => (Array.isArray(data) ? data : (data?.results || []));

const MedicalRecords = () => {
  const { token, initializing, user } = useAuth();
  const confirm = useConfirm();
  const [searchParams] = useSearchParams();

  const [records,          setRecords]          = useState([]);
  const [pets,             setPets]             = useState([]);
  const [isLoadingPets,    setIsLoadingPets]    = useState(true);
  const [products,         setProducts]         = useState([]);
  const productMap = useMemo(() => {
    const map = {};
    products.forEach(p => { map[p.id] = p; });
    return map;
  }, [products]);
  const [loading,          setLoading]          = useState(true);
  const [totalCount,       setTotalCount]       = useState(0);
  const [page,             setPage]             = useState(1);
  const [totalPages,       setTotalPages]       = useState(1);

  const [selectedPet,      setSelectedPet]      = useState("");
  const [typeFilter,       setTypeFilter]       = useState("all");
  const [petSearch,        setPetSearch]        = useState("");
  const [historySearch,    setHistorySearch]    = useState("");
  const [expandedId,       setExpandedId]       = useState(null);
  const [petCounts,        setPetCounts]        = useState({});

  const [showStepper,      setShowStepper]      = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [editingRecord,    setEditingRecord]    = useState(null);
  const [showPrescriptionModal,  setShowPrescriptionModal]  = useState(false);
  const [prescriptionTarget,     setPrescriptionTarget]     = useState(null);
  const [downloadingPrescriptionId, setDownloadingPrescriptionId] = useState(null);

  useEffect(() => { if (token) loadAllData(); }, [token]);
  useEffect(() => { if (token) loadRecords(); }, [selectedPet, page, token]);

  useEffect(() => {
    if (!selectedPet || pets.length === 0) return;
    if (!pets.some(p => String(p.id) === String(selectedPet))) setSelectedPet("");
  }, [selectedPet, pets]);

  useEffect(() => {
    const petParam = searchParams.get("pet");
    const appointmentParam = searchParams.get("appointment");
    if (petParam) {
      setSelectedPet(petParam);
      if (appointmentParam) {
        setShowStepper(true);
      }
    }
  }, [searchParams, token]);

  const loadAllData = async () => {
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

  const refreshAfterMutation = () => loadRecords();

  const filteredByType = useMemo(() => {
    if (typeFilter === "all") return records;
    return records.filter(r => {
      const mapped = TYPE_FILTER_MAP[r.consultation_type] || r.consultation_type;
      return mapped === typeFilter;
    });
  }, [records, typeFilter]);

  const visibleRecords = useMemo(() => {
    if (!historySearch.trim()) return filteredByType;
    const q = historySearch.toLowerCase();
    return filteredByType.filter(r =>
      (r.diagnosis || "").toLowerCase().includes(q) ||
      (r.treatment || "").toLowerCase().includes(q) ||
      (r.notes || "").toLowerCase().includes(q) ||
      (r.veterinarian_name || "").toLowerCase().includes(q)
    );
  }, [filteredByType, historySearch]);

  const petInfo = selectedPet ? pets.find(p => String(p.id) === String(selectedPet)) : null;

  const handleSelectPet = (petId) => {
    setSelectedPet(String(petId));
    setPage(1);
    setExpandedId(null);
  };

  const handleCloseRecord = async (record) => {
    const ok = await confirm({
      title: "Finalizar consulta",
      message: "La consulta quedará cerrada y no podrás modificar productos o servicios.",
      confirmText: "Finalizar",
      dangerMode: false,
    });
    if (!ok) return;

    try {
      const p = closeMedicalRecord(token, record.public_id).then(() => refreshAfterMutation());
      await toast.promise(p, {
        loading: 'Finalizando...',
        success: 'Consulta finalizada',
        error: (err) => apiError(err, "No se pudo finalizar la consulta")
      });
    } catch {}
  };

  const handleDelete = async (publicId) => {
    const ok = await confirm({
      title: "Eliminar consulta",
      message: "Se eliminará el registro clínico de esta consulta. Esta acción no se puede deshacer.",
      confirmText: "Eliminar",
      dangerMode: true,
    });
    if (!ok) return;
    try {
      const p = deleteMedicalRecord(token, publicId).then(() => loadRecords());
      await toast.promise(p, { loading: 'Eliminando...', success: 'Consulta eliminada', error: 'Error al eliminar' });
    } catch {}
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
        await loadRecords();
        closePrescriptionModal();
      });
      await toast.promise(p, { loading: 'Creando receta...', success: 'Receta creada', error: 'Error al crear receta' });
    } catch {}
  };

  const handleStepperComplete = async () => {
    setShowStepper(false);
    setEditingRecord(null);
    await loadRecords();
    await loadAllData();
  };

  const handleStepperClose = async () => {
    setShowStepper(false);
    setEditingRecord(null);
    await loadRecords();
    await loadAllData();
  };

  const handleOpenStepper = () => {
    if (!selectedPet) {
      toast.error("Selecciona una mascota primero");
      return;
    }
    setEditingRecord(null);
    setShowStepper(true);
    setSidebarCollapsed(true);
  };

  if (initializing || loading) {
    return (
      <Layout>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
          <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando historial clínico...</p>
        </div>
      </Layout>
    );
  }

  const canCreate = user?.role !== "ASSISTANT";

  return (
    <Layout>
      <div className={styles.pageLayout}>
        <PetSidebar
          pets={pets}
          petCounts={petCounts}
          selectedPet={selectedPet}
          petSearch={petSearch}
          onSelectPet={handleSelectPet}
          onPetSearch={setPetSearch}
          isLoadingPets={isLoadingPets}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(c => !c)}
        />

        {showStepper && selectedPet ? (
          <ConsultationStepperV2
            pet={petInfo}
            products={products}
            productMap={productMap}
            onClose={handleStepperClose}
            onComplete={handleStepperComplete}
            initialRecord={editingRecord}
          />
        ) : (
            <main className={styles.mainContent}>
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
                  <div className={styles.patientHeader}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <PatientHeader
                        pet={petInfo}
                        latestVitals={records[0]?.latest_vitals || null}
                        noPadding={true}
                      />
                      {canCreate && (
                        <button className="btn btn-primary btn-md" style={{ background: '#1a4434' }} onClick={handleOpenStepper}>
                          + Nueva Consulta
                        </button>
                      )}
                    </div>
                  </div>

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
                      <span className={styles.historySearchIcon}><Icon.Search /></span>
                      <input
                        className={styles.historySearchInput}
                        placeholder="Buscar en historial..."
                        value={historySearch}
                        onChange={e => setHistorySearch(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className={styles.timeline}>
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
                      <Timeline
                        records={visibleRecords}
                        expandedId={expandedId}
                        onToggleExpand={setExpandedId}
                        onCloseRecord={handleCloseRecord}
                        onEdit={(record) => {
                          setEditingRecord(record);
                          setActiveRecordId(record.public_id);
                          setShowStepper(true);
                        }}
                        onDelete={handleDelete}
                        onCreatePrescription={openPrescriptionModal}
                        onDownloadPrescription={handleDownloadPrescription}
                        downloadingPrescriptionId={downloadingPrescriptionId}
                        user={user}
                        canCreate={canCreate}
                      />
                    )}

                    {totalPages > 1 && (
                      <div className={styles.pagination}>
                        <button className="btn btn-secondary btn-sm" disabled={page === 1}
                          onClick={() => setPage(p => Math.max(1, p - 1))}>Anterior</button>
                        <span className={styles.paginationLabel}>Página {page} de {totalPages}</span>
                        <button className="btn btn-secondary btn-sm" disabled={page === totalPages}
                          onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Siguiente</button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </main>
        )}
      </div>

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
    </Layout>
  );
};

export default MedicalRecords;
