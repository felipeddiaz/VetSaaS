import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Icon } from "../../components/icons";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { useAuth } from "../../auth/authContext";
import {
  createMedicalRecord,
  updateMedicalRecord,
  closeMedicalRecord,
  getMedicalRecord,
} from "../../api/medicalRecords";
import { createVitals, getSummary } from "../../api/vitals";
import {
  addMedicalRecordProduct,
  removeMedicalRecordProduct,
  getMedicalRecordProducts,
} from "../../api/inventory";
import { createPrescription, updatePrescription } from "../../api/prescriptions";
import {
  getMedicalRecordServices,
  addMedicalRecordService,
  removeMedicalRecordService,
} from "../../api/medicalRecords";
import SearchSelect from "../../components/SearchSelect";
import styles from "./stepperV2.module.css";

const CONSULTATION_TYPES = [
  { value: "general", label: "General", desc: "Chequeo, control", icon: <Icon.Paw s={20} /> },
  { value: "vaccine", label: "Vacuna", desc: "Inmunización", icon: <Icon.Syringe s={20} /> },
  { value: "surgery", label: "Cirugía", desc: "Proc. quirúrgico", icon: <Icon.Activity s={20} /> },
  { value: "emergency", label: "Urgencia", desc: "Atención inmediata", icon: <Icon.AlertTriangle s={20} /> },
];

const STEPS = [
  { id: 1, label: "Paciente y diagnóstico" },
  { id: 2, label: "Tratamiento y receta" },
  { id: 3, label: "Productos e insumos" },
  { id: 4, label: "Facturación" },
];

const FIELD_TO_STEP = {
  consultation_type: 1,
  diagnosis: 1,
  notes: 1,
  treatment: 2,
  weight: 2,
  products: 3,
  services: 3,
  prescription: 2,
};

const normalizeVitals = (draft) => ({
  weight: toNumberOrNull(draft.weight),
  temperature: toNumberOrNull(draft.temperature),
  heart_rate: toNumberOrNull(draft.heart_rate),
  respiratory_rate: toNumberOrNull(draft.respiratory_rate),
});

const toNumberOrNull = (v) => {
  if (v === "" || v == null) return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
};

export default function ConsultationStepperV2({
  pet,
  products = [],
  productMap = {},
  onClose,
  onComplete,
  initialRecord = null,
}) {
  const { token, user } = useAuth();
  const isEditing = initialRecord && initialRecord.id;

  // Referencia centralizada para IDs (evita desincronización)
  const [recordRef, setRecordRef] = useState({ publicId: null, id: null });

  useEffect(() => {
    if (isEditing && initialRecord) {
      setRecordRef({
        publicId: initialRecord.public_id,
        id: initialRecord.id,
      });
    } else {
      setRecordRef({ publicId: null, id: null });
    }
  }, [initialRecord, isEditing]);

  const [step, setStep] = useState(1);
  const [prescriptionId, setPrescriptionId] = useState(initialRecord?.prescription_id || null);

  // Guardar updated_at inicial para anti-stale check
  const [initialUpdatedAt, setInitialUpdatedAt] = useState(
    isEditing && initialRecord?.updated_at
      ? new Date(initialRecord.updated_at).getTime()
      : null
  );

  const [draft, setDraft] = useState(() => {
    if (isEditing) {
      const v = initialRecord.latest_vitals || {};
      return {
        consultation_type: initialRecord.consultation_type || "general",
        diagnosis: initialRecord.diagnosis || "",
        treatment: initialRecord.treatment || "",
        notes: initialRecord.notes || "",
        weight: v.weight ?? initialRecord.weight ?? "",
        temperature: v.temperature != null ? String(v.temperature) : "",
        heart_rate: v.heart_rate != null ? String(v.heart_rate) : "",
        respiratory_rate: v.respiratory_rate != null ? String(v.respiratory_rate) : "",
      };
    }
    return {
      consultation_type: "general",
      diagnosis: "",
      treatment: "",
      notes: "",
      weight: "",
      temperature: "",
      heart_rate: "",
      respiratory_rate: "",
    };
  });

  // Prescription draft state
  const [prescriptionDraft, setPrescriptionDraft] = useState({
    items: initialRecord?.prescription_summary?.items || [],
    notes: initialRecord?.prescription_summary?.notes || "",
  });
  const [recipeLine, setRecipeLine] = useState({ product: null, dose: "", duration: "", quantity: "1" });

  // Hash para detectar cambios en vitales (evita duplicados)
  const lastVitalsHash = useRef(null);
  // Hash para detectar cambios en receta (evita saves innecesarios)
  const lastPrescriptionHash = useRef(null);

  const [addedProducts, setAddedProducts] = useState([]);
  const [productLine, setProductLine] = useState({ product: null, quantity: "1" });
  const [saving, setSaving] = useState(false);
  const [forceWeight, setForceWeight] = useState(false);

  // Servicios de consulta
  const [availableServices, setAvailableServices] = useState([]);
  const [addedServices, setAddedServices] = useState([]);
  const [serviceLine, setServiceLine] = useState({ service: null, quantity: "1" });

  // Errores de validación inline
  const [formErrors, setFormErrors] = useState({});

  // Summary state con requestSeq para evitar race conditions
  const [summary, setSummary] = useState(null);
  const requestSeq = useRef(0);

  const refreshSummary = useCallback(async () => {
    if (!recordRef.publicId) return;
    const seq = ++requestSeq.current;
    try {
      const data = await getSummary(recordRef.publicId);
      if (seq === requestSeq.current) {
        setSummary(data);
      }
    } catch {
      // Silencioso - el resumen es informativo
    }
  }, [recordRef.publicId]);

  // Cargar productos y servicios existentes al montar
  useEffect(() => {
    if (recordRef.publicId) {
      const loadProducts = async () => {
        try {
          const data = await getMedicalRecordProducts(recordRef.publicId);
          const normalized = (Array.isArray(data) ? data : (data?.results || [])).map(p => ({
            id: p.id,
            product_name: p.product_name,
            presentation_name: p.presentation_name,
            quantity: p.quantity,
            unit_price: p.unit_price,
          }));
          setAddedProducts(normalized);
        } catch { }
      };
      const loadServices = async () => {
        try {
          const data = await getMedicalRecordServices(recordRef.publicId);
          const normalized = (Array.isArray(data) ? data : (data?.results || [])).map(s => ({
            id: s.id,
            service: s.service,
            name: s.service_name,
            quantity: s.quantity,
            price: s.unit_price,
          }));
          setAddedServices(normalized);
        } catch { }
      };
      loadProducts();
      loadServices();
      refreshSummary();
    }
  }, [recordRef.publicId]);

  // Cargar servicios disponibles al montar
  useEffect(() => {
    const loadServices = async () => {
      try {
        const res = await fetch('/api/billing/services/?active=true', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        setAvailableServices(Array.isArray(data) ? data : (data?.results || []));
      } catch { }
    };
    loadServices();
  }, [token]);

  // Search logic for SearchSelect
  const handleProductSearch = async (q) => {
    const lower = q.trim().toLowerCase();
    if (!lower) return products.slice(0, 8).map((p) => ({ id: p.id, label: p.name }));
    return products
      .filter(
        (p) =>
          p.name?.toLowerCase().includes(lower) ||
          (p.sku && p.sku.toLowerCase().includes(lower))
      )
      .slice(0, 8)
      .map((p) => ({ id: p.id, label: p.name }));
  };

  // Anti-stale check antes de mutaciones críticas
  const checkNotStale = async () => {
    if (!recordRef.publicId || !initialUpdatedAt) return true;
    try {
      const fresh = await getMedicalRecord(token, recordRef.publicId);
      if (fresh.status !== 'open') {
        toast.error('La consulta ya no está abierta.');
        return false;
      }
      const freshTs = new Date(fresh.updated_at).getTime();
      if (freshTs !== initialUpdatedAt) {
        toast.warning('La consulta fue modificada por otro usuario. Recargando...');
        onClose?.(recordRef.id);
        return false;
      }
      return true;
    } catch {
      return true; // Si falla el check, continuar (degradado)
    }
  };

  const handleSave = async (fromStep) => {
    setSaving(true);
    setFormErrors({}); // Limpiar errores previos
    try {
      // Anti-stale check antes de mutar
      const isOk = await checkNotStale();
      if (!isOk) return;

      let resultId = recordRef.id;
      let resultPublicId = recordRef.publicId;

      // 1. Save Medical Record
      if (!recordRef.publicId) {
        const result = await createMedicalRecord(token, {
          pet: pet.id,
          consultation_type: draft.consultation_type,
          diagnosis: draft.diagnosis,
          treatment: draft.treatment,
          notes: draft.notes,
        });
        resultId = result.id;
        resultPublicId = result.public_id;
        setRecordRef({ publicId: resultPublicId, id: resultId });
      } else {
        await updateMedicalRecord(token, recordRef.publicId, {
          consultation_type: draft.consultation_type,
          diagnosis: draft.diagnosis,
          treatment: draft.treatment,
          notes: draft.notes,
        });
      }

      // 2. Save Vitals solo si cambiaron (hash comparison)
      const vitalFields = ["weight", "temperature", "heart_rate", "respiratory_rate"];
      const vitalsPayload = normalizeVitals(draft);
      const hasVitals = vitalFields.some(f => draft[f] !== "" && draft[f] != null);
      const currentVitalsHash = JSON.stringify(vitalsPayload);

      if (hasVitals && currentVitalsHash !== lastVitalsHash.current) {
        try {
          await createVitals(resultPublicId, {
            ...vitalsPayload,
            force_weight: forceWeight,
          });
          lastVitalsHash.current = currentVitalsHash;
          setForceWeight(false); // Reset después de éxito
        } catch (err) {
          // Detectar force_weight_required por meta
          const requiresForceWeight = err?.response?.data?.meta?.force_weight_required;
          if (requiresForceWeight) {
            setForceWeight(true);
            toast.error('Cambio brusco de peso detectado. Presiona "Siguiente" para confirmar.');
            return; // No avanzar, permitir reintento
          }
          throw err; // Re-lanzar otros errores
        }
      }

      // 3. Handle Prescription solo si cambió (hash comparison)
      const currentPrescriptionHash = JSON.stringify({
        items: prescriptionDraft.items.map(i => `${i.product}-${i.quantity}-${i.dose}`),
        notes: prescriptionDraft.notes,
      });

      if (prescriptionDraft.items.length > 0 && currentPrescriptionHash !== lastPrescriptionHash.current) {
        const pPayload = {
          pet: pet.id,
          medical_record: resultId, // FK usa id entero
          notes: prescriptionDraft.notes,
          items: prescriptionDraft.items.map(it => ({
            product: it.product_id || it.product,
            quantity: it.quantity,
            dose: it.dose,
            duration: it.duration
          }))
        };
        if (prescriptionId) {
          await updatePrescription(prescriptionId, pPayload);
        } else {
          const pResult = await createPrescription(pPayload);
          setPrescriptionId(pResult.id);
        }
        lastPrescriptionHash.current = currentPrescriptionHash;
      }

      // Éxito: limpiar errores y avanzar
      setFormErrors({});
      if (fromStep < 4) {
        setStep(fromStep + 1);
      } else {
        handleFinalize(resultPublicId);
      }
    } catch (err) {
      // Capturar errores de validación por campo
      const fieldErrors = err?.response?.data?.errors || {};

      // Mostrar primer error en toast (solo si es string legible)
      const firstField = Object.keys(fieldErrors)[0];
      const firstMsg = firstField && Array.isArray(fieldErrors[firstField])
        ? fieldErrors[firstField][0]
        : null;

      if (typeof firstMsg === 'string') {
        toast.error(firstMsg);
      } else {
        toast.error(apiError(err, "Error al guardar"));
      }

      // Setear errores inline para el formulario
      setFormErrors(fieldErrors);

      // Navegar al paso con error (solo el primero detectado)
      const targetStep = firstField ? FIELD_TO_STEP[firstField] : null;
      if (targetStep && targetStep !== step) {
        setStep(targetStep);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleFinalize = async (id) => {
    const targetId = id || recordRef.publicId;
    if (!targetId) return;

    // Anti-stale check final
    const isOk = await checkNotStale();
    if (!isOk) return;

    setSaving(true);
    try {
      await closeMedicalRecord(token, targetId);
      toast.success("Consulta finalizada exitosamente");
      onComplete?.(recordRef.id);
      onClose?.();
    } catch (err) {
      toast.error(apiError(err, "Error al finalizar"));
    } finally {
      setSaving(false);
    }
  };

  const handleAddRecipeItem = () => {
    if (!recipeLine.product) return;
    const selected = productMap[recipeLine.product.id];
    if (!selected) return;

    const newItem = {
      product: selected.id,
      product_id: selected.id,
      product_name: selected.name,
      quantity: recipeLine.quantity,
      dose: recipeLine.dose,
      duration: recipeLine.duration,
    };

    setPrescriptionDraft(prev => ({
      ...prev,
      items: [...prev.items, newItem]
    }));
    setRecipeLine({ product: null, dose: "", duration: "", quantity: "1" });
  };

  const handleRemoveRecipeItem = (index) => {
    setPrescriptionDraft(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index)
    }));
  };

  const handleAddProduct = async () => {
    if (!productLine.product) return;
    const selected = productMap[productLine.product.id];
    if (!selected?.presentation?.id) {
      toast.error("Selecciona un producto con presentación");
      return;
    }
    try {
      const result = await addMedicalRecordProduct(recordRef.publicId, {
        presentation: selected.presentation.id,
        quantity: productLine.quantity,
      });
      setAddedProducts(prev => [...prev, {
        id: result.id,
        product_name: selected.name,
        presentation_name: selected.presentation.name,
        quantity: result.quantity,
        unit_price: result.unit_price,
      }]);
      setProductLine({ product: null, quantity: "1" });
      toast.success("Producto agregado");
      refreshSummary();
    } catch (err) {
      toast.error(apiError(err, "Error al agregar producto"));
    }
  };

  const handleRemoveProduct = async (productEntryId) => {
    const prev = [...addedProducts];
    setAddedProducts(prev.filter(p => p.id !== productEntryId));
    try {
      await removeMedicalRecordProduct(recordRef.publicId, productEntryId);
      toast.success("Producto eliminado");
      refreshSummary();
    } catch (err) {
      setAddedProducts(prev); // Rollback
      toast.error(apiError(err, "No se pudo eliminar el producto"));
    }
  };

  const handleAddService = async () => {
    if (!serviceLine.service) return;
    const selected = availableServices.find(s => s.id === serviceLine.service);
    if (!selected) return;

    // Validar unicidad
    if (addedServices.some(s => s.service === selected.id)) {
      toast.error("Este servicio ya fue agregado");
      return;
    }

    try {
      const result = await addMedicalRecordService(recordRef.publicId, {
        service: selected.id,
        quantity: serviceLine.quantity,
      });
      setAddedServices(prev => [...prev, {
        id: result.id,
        service: selected.id,
        name: selected.name,
        quantity: result.quantity,
        price: selected.base_price,
      }]);
      setServiceLine({ service: null, quantity: "1" });
      toast.success("Servicio agregado");
      refreshSummary();
    } catch (err) {
      toast.error(apiError(err, "Error al agregar servicio"));
    }
  };

  const handleRemoveService = async (serviceEntryId) => {
    const prev = [...addedServices];
    setAddedServices(prev.filter(s => s.id !== serviceEntryId));
    try {
      await removeMedicalRecordService(recordRef.publicId, serviceEntryId);
      toast.success("Servicio eliminado");
      refreshSummary();
    } catch (err) {
      setAddedServices(prev); // Rollback
      toast.error(apiError(err, "No se pudo eliminar el servicio"));
    }
  };

  // Totales desde summary (backend) en lugar de hardcodeo
  const totalBilling = useMemo(() => {
    if (summary?.totals) {
      return {
        subtotal: summary.totals.subtotal,
        tax: summary.totals.tax_amount,
        total: summary.totals.total,
        status: summary.totals.status,
      };
    }
    // Fallback a cálculo local si no hay summary
    const prodsTotal = addedProducts.reduce((sum, p) => sum + (Number(p.unit_price) * Number(p.quantity)), 0);
    return { subtotal: prodsTotal, tax: 0, total: prodsTotal, status: 'draft' };
  }, [summary, addedProducts]);

  return (
    <div className={styles.fullPageContainer}>
      <div className={styles.mainWorkArea}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <div className={styles.breadcrumbs}>
              <span>VetCare</span> / <span>Historial Clínico</span>
            </div>
            <div className={styles.headerActions}>
              <button className="btn btn-secondary btn-sm" onClick={() => onClose()}>
                Cerrar
              </button>
              <button className={`${styles.btnFinalizar} btn btn-sm`} onClick={() => handleFinalize()}>
                <Icon.Check s={14} /> Finalizar
              </button>
            </div>
          </div>
        </div>

        <div className={styles.stepperBar}>
          <div className={styles.stepTabs}>
            {STEPS.map((s) => {
              const isActive    = step === s.id;
              const isCompleted = step > s.id;
              return (
                <div
                  key={s.id}
                  className={`${styles.stepTab} ${isActive ? styles.stepTabActive : ""} ${isCompleted ? styles.stepTabDone : ""}`}
                >
                  <div className={styles.stepTabNum}>
                    {isCompleted ? <Icon.Check s={12} /> : s.id}
                  </div>
                  <span className={styles.stepTabLabel}>{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className={styles.contentArea}>
          {step === 1 && (
            <div className="fade-in">
              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>Tipo de consulta</h2>
              </div>
              <div className={styles.typeGrid}>
                {CONSULTATION_TYPES.map(t => (
                  <div key={t.value}
                    className={`${styles.typeCard} ${draft.consultation_type === t.value ? styles.typeCardActive : ""}`}
                    onClick={() => setDraft(d => ({ ...d, consultation_type: t.value }))}
                  >
                    <div className={styles.typeIcon}>{t.icon}</div>
                    <div>
                      <div className={styles.typeName}>{t.label}</div>
                      <div className={styles.typeDesc}>{t.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>Motivo y diagnóstico</h2>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.inputLabel}>Motivo de consulta</label>
                <textarea
                  className={`${styles.textarea} ${formErrors.notes ? styles.fieldError : ''}`}
                  rows={2}
                  placeholder="Tos seca persistente"
                  value={draft.notes}
                  onChange={e => {
                    setDraft(d => ({ ...d, notes: e.target.value }));
                    if (formErrors.notes) setFormErrors(prev => ({ ...prev, notes: undefined }));
                  }}
                />
                {formErrors.notes && (
                  <div className={styles.fieldErrorMessage}>{formErrors.notes[0]}</div>
                )}
              </div>

              <div className={styles.formGroup}>
                <label className={styles.inputLabel}>Diagnóstico clínico</label>
                <textarea
                  className={`${styles.textarea} ${formErrors.diagnosis ? styles.fieldError : ''}`}
                  rows={3}
                  placeholder="Bronquitis aguda"
                  value={draft.diagnosis}
                  onChange={e => {
                    setDraft(d => ({ ...d, diagnosis: e.target.value }));
                    if (formErrors.diagnosis) setFormErrors(prev => ({ ...prev, diagnosis: undefined }));
                  }}
                />
                {formErrors.diagnosis && (
                  <div className={styles.fieldErrorMessage}>{formErrors.diagnosis[0]}</div>
                )}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="fade-in">
              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>Tratamiento e Indicaciones</h2>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.inputLabel}>Indicaciones generales (Tratamiento)</label>
                <textarea
                  className={`${styles.textarea} ${formErrors.treatment ? styles.fieldError : ''}`}
                  rows={4}
                  placeholder="Instrucciones detalladas del tratamiento..."
                  value={draft.treatment}
                  onChange={e => {
                    setDraft(d => ({ ...d, treatment: e.target.value }));
                    if (formErrors.treatment) setFormErrors(prev => ({ ...prev, treatment: undefined }));
                  }}
                />
                {formErrors.treatment && (
                  <div className={styles.fieldErrorMessage}>{formErrors.treatment[0]}</div>
                )}
              </div>

              <div className={styles.recipeSection}>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Receta médica (Medicamentos)</h2>
                </div>

                <div style={{ background: '#f9f9f9', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 60px 80px', gap: '8px', alignItems: 'end' }}>
                    <div>
                      <label className={styles.inputLabel}>Medicamento</label>
                      <SearchSelect
                        placeholder="Buscar..."
                        value={recipeLine.product}
                        onChange={item => setRecipeLine(prev => ({ ...prev, product: item }))}
                        onSearch={handleProductSearch}
                      />
                    </div>
                    <div>
                      <label className={styles.inputLabel}>Dosis</label>
                      <input className={styles.textarea} style={{ height: '38px', padding: '0 8px' }} placeholder="50mg c/12h" value={recipeLine.dose} onChange={e => setRecipeLine(p => ({ ...p, dose: e.target.value }))} />
                    </div>
                    <div>
                      <label className={styles.inputLabel}>Duración</label>
                      <input className={styles.textarea} style={{ height: '38px', padding: '0 8px' }} placeholder="7 días" value={recipeLine.duration} onChange={e => setRecipeLine(p => ({ ...p, duration: e.target.value }))} />
                    </div>
                    <div>
                      <label className={styles.inputLabel}>Cant.</label>
                      <input type="number" className={styles.textarea} style={{ height: '38px', padding: '0 8px' }} value={recipeLine.quantity} onChange={e => setRecipeLine(p => ({ ...p, quantity: e.target.value }))} />
                    </div>
                    <button className="btn btn-primary btn-md" style={{ height: '38px' }} onClick={handleAddRecipeItem} disabled={!recipeLine.product}>
                      +
                    </button>
                  </div>
                </div>

                <div className={styles.recipeList}>
                  {prescriptionDraft.items.length === 0 ? (
                    <p style={{ color: '#999', fontSize: '13px', fontStyle: 'italic', padding: '10px' }}>No hay medicamentos en la receta</p>
                  ) : prescriptionDraft.items.map((item, idx) => (
                    <div key={idx} className={styles.recipeItem}>
                      <Icon.Pill s={16} className={styles.recipeIcon} />
                      <div className={styles.recipeName}>{item.product_name || productMap[item.product_id || item.product]?.name}</div>
                      <div className={styles.recipeDetails}>{item.dose} · {item.duration} · {item.quantity} unidades</div>
                      <button className="btn btn-ghost btn-xs" style={{ color: '#ef4444' }} onClick={() => handleRemoveRecipeItem(idx)}>
                        <Icon.Trash s={14} />
                      </button>
                    </div>
                  ))}
                </div>

                <div className={styles.formGroup} style={{ marginTop: '16px' }}>
                  <label className={styles.inputLabel}>Notas adicionales para la receta</label>
                  <textarea
                    className={styles.textarea}
                    rows={2}
                    placeholder="Observaciones de la receta..."
                    value={prescriptionDraft.notes}
                    onChange={e => setPrescriptionDraft(p => ({ ...p, notes: e.target.value }))}
                  />
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="fade-in">
              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>Productos e Insumos consumidos</h2>
                <p style={{ fontSize: '12px', color: '#888', marginLeft: 'auto' }}>Estos productos se descargarán del inventario</p>
              </div>

              <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
                <div style={{ flex: 1 }}>
                  <SearchSelect
                    placeholder="Buscar producto..."
                    value={productLine.product}
                    onChange={item => setProductLine(prev => ({ ...prev, product: item }))}
                    onSearch={handleProductSearch}
                  />
                </div>
                <div style={{ width: '80px' }}>
                  <input
                    type="number"
                    className={styles.textarea}
                    style={{ height: '38px', padding: '0 10px' }}
                    value={productLine.quantity}
                    onChange={e => setProductLine(prev => ({ ...prev, quantity: e.target.value }))}
                    min="1"
                  />
                </div>
                <button
                  className="btn btn-primary btn-md"
                  onClick={handleAddProduct}
                  disabled={!productLine.product}
                >
                  Agregar
                </button>
              </div>

              <div className={styles.tableContainer}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Producto</th>
                      <th>Cant.</th>
                      <th>P. Unit</th>
                      <th>Subtotal</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {addedProducts.length === 0 ? (
                      <tr>
                        <td colSpan="5" style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
                          No hay productos registrados en esta consulta.
                        </td>
                      </tr>
                    ) : addedProducts.map(p => (
                      <tr key={p.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{p.product_name}</div>
                          <div style={{ fontSize: '11px', color: '#888' }}>{p.presentation_name}</div>
                        </td>
                        <td style={{ textAlign: 'center' }}>{p.quantity}</td>
                        <td style={{ textAlign: 'center' }}>${Number(p.unit_price).toFixed(2)}</td>
                        <td style={{ textAlign: 'center' }}>${(Number(p.unit_price) * Number(p.quantity)).toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-ghost btn-xs"
                            style={{ color: '#ef4444' }}
                            onClick={() => handleRemoveProduct(p.id)}
                          >
                            <Icon.Trash s={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className={styles.sectionHeader} style={{ marginTop: '32px' }}>
                <h2 className={styles.sectionTitle}>Servicios profesionales</h2>
              </div>

              <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
                <div style={{ flex: 1 }}>
                  <SearchSelect
                    placeholder="Buscar servicio..."
                    value={serviceLine.service}
                    onChange={item => setServiceLine(prev => ({ ...prev, service: item }))}
                    onSearch={async (q) => {
                      const lower = q.trim().toLowerCase();
                      if (!lower) return availableServices.slice(0, 8).map(s => ({ id: s.id, label: s.name }));
                      return availableServices
                        .filter(s => s.name?.toLowerCase().includes(lower))
                        .slice(0, 8)
                        .map(s => ({ id: s.id, label: s.name }));
                    }}
                  />
                </div>
                <div style={{ width: '80px' }}>
                  <input
                    type="number"
                    className={styles.textarea}
                    style={{ height: '38px', padding: '0 10px' }}
                    value={serviceLine.quantity}
                    onChange={e => setServiceLine(prev => ({ ...prev, quantity: e.target.value }))}
                    min="1"
                  />
                </div>
                <button
                  className="btn btn-primary btn-md"
                  onClick={handleAddService}
                  disabled={!serviceLine.service}
                >
                  Agregar
                </button>
              </div>

              <div className={styles.tableContainer}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Servicio</th>
                      <th>Cant.</th>
                      <th>P. Unit</th>
                      <th>Subtotal</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {addedServices.length === 0 ? (
                      <tr>
                        <td colSpan="5" style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
                          No hay servicios registrados en esta consulta.
                        </td>
                      </tr>
                    ) : addedServices.map(s => (
                      <tr key={s.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{s.name}</div>
                        </td>
                        <td style={{ textAlign: 'center' }}>{s.quantity}</td>
                        <td style={{ textAlign: 'center' }}>${Number(s.price).toFixed(2)}</td>
                        <td style={{ textAlign: 'center' }}>${(Number(s.price) * Number(s.quantity)).toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-ghost btn-xs"
                            style={{ color: '#ef4444' }}
                            onClick={() => handleRemoveService(s.id)}
                          >
                            <Icon.Trash s={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="fade-in">
              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>Resumen y Facturación</h2>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
                <div>
                  <h3 style={{ fontSize: '14px', fontWeight: '700', marginBottom: '16px' }}>Resumen Clínico</h3>
                  <div className={styles.resumenCard}>
                    <div className={styles.expandedSection}>
                      <div className={styles.expandedLabel}>Diagnóstico</div>
                      <div className={styles.expandedText}>{draft.diagnosis || <span style={{ color: "var(--c-text-3)", fontStyle: "italic" }}>Sin diagnóstico</span>}</div>
                    </div>
                    <div className={styles.expandedSection} style={{ marginTop: '12px' }}>
                      <div className={styles.expandedLabel}>Tratamiento</div>
                      <div className={styles.expandedText}>{draft.treatment || <span style={{ color: "var(--c-text-3)", fontStyle: "italic" }}>Sin indicaciones</span>}</div>
                    </div>
                    <div className={styles.expandedSection} style={{ marginTop: '12px' }}>
                      <div className={styles.expandedLabel}>Medicamentos Recetados</div>
                      <div className={styles.expandedText}>
                        {prescriptionDraft.items.length === 0 ? "Sin medicamentos" : `${prescriptionDraft.items.length} items`}
                      </div>
                    </div>
                    <div className={styles.expandedSection} style={{ marginTop: '12px' }}>
                      <div className={styles.expandedLabel}>Servicios</div>
                      <div className={styles.expandedText}>
                        {addedServices.length === 0 ? "Sin servicios" : `${addedServices.length} servicios`}
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 style={{ fontSize: '14px', fontWeight: '700', marginBottom: '16px' }}>Facturación</h3>
                  <div className={styles.resumenCard} style={{ background: '#f8f9fa' }}>
                    {summary?.totals ? (
                      <>
                        <div className={styles.resumenRow}>
                          <span>Subtotal</span>
                          <span>${Number(summary.totals.subtotal).toFixed(2)}</span>
                        </div>
                        <div className={styles.resumenRow}>
                          <span>Impuesto</span>
                          <span>${Number(summary.totals.tax_amount).toFixed(2)}</span>
                        </div>
                        <div className={`${styles.resumenRow} ${styles.subtotalHighlight}`} style={{ fontSize: '18px', marginTop: '16px', borderTop: '2px solid #ddd' }}>
                          <span>TOTAL A PAGAR</span>
                          <span>${Number(summary.totals.total).toFixed(2)}</span>
                        </div>
                        <div style={{ marginTop: '8px' }}>
                          <span className="badge badge-info">
                            {summary.totals.status === 'draft' ? 'Borrador' :
                              summary.totals.status === 'confirmed' ? 'Confirmada' :
                                summary.totals.status === 'paid' ? 'Pagada' : 'Cancelada'}
                          </span>
                        </div>
                        <p style={{ fontSize: '11px', color: '#888', marginTop: '20px' }}>
                          * Al finalizar, se generará una cuenta por cobrar para el tutor.
                        </p>
                      </>
                    ) : (
                      <>
                        <div className={styles.resumenRow}>
                          <span>Productos e insumos</span>
                          <span>${totalBilling.subtotal.toFixed(2)}</span>
                        </div>
                        <div className={`${styles.resumenRow} ${styles.subtotalHighlight}`} style={{ fontSize: '18px', marginTop: '16px', borderTop: '2px solid #ddd' }}>
                          <span>TOTAL ESTIMADO</span>
                          <span>${totalBilling.total.toFixed(2)}</span>
                        </div>
                        <p style={{ fontSize: '11px', color: '#888', marginTop: '20px' }}>
                          * Los totales se calcularán al finalizar.
                        </p>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={styles.footer}>
          <button className="btn btn-secondary btn-md" disabled={step === 1} onClick={() => setStep(s => s - 1)}>
            <Icon.ChevronLeft s={16} /> Anterior
          </button>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              className="btn btn-primary btn-md"
              style={{ background: '#1a4434' }}
              onClick={() => handleSave(step)}
              disabled={saving}
            >
              {step === 4 ? 'Finalizar Consulta' : 'Siguiente'} <Icon.ChevronRight s={16} />
            </button>
          </div>
        </div>
      </div>

      <aside className={styles.rightSidebar}>
        <section className={styles.sidebarSection}>
          <div className={styles.patientCard}>
            <div className={styles.patientMainInfo}>
              <div className={styles.avatar}>{(pet?.name?.[0] || 'P').toUpperCase()}</div>
              <div>
                <div style={{ fontSize: '11px', color: '#aaa', textTransform: 'uppercase', fontWeight: '700', letterSpacing: '0.05em', marginBottom: '2px' }}>Paciente</div>
                <h4 className={styles.patientName}>{pet?.name || "—"}</h4>
                <div className={styles.patientMeta}>{pet?.species || "—"} · {pet?.breed || "—"}</div>
              </div>
            </div>
            <div className={styles.patientDetailGrid}>
              <div className={styles.detailItem}>
                <div className={styles.detailLabel}>Tutor</div>
                <div className={styles.detailVal}>{pet?.owner?.name || pet?.owner_name || "No asignado"}</div>
              </div>
              <div className={styles.detailItem}>
                <div className={styles.detailLabel}>Teléfono</div>
                <div className={styles.detailVal}>{pet?.owner?.phone || "—"}</div>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.sidebarSection}>
          <div style={{ fontSize: '11px', color: '#aaa', textTransform: 'uppercase', fontWeight: '700', letterSpacing: '0.05em', marginBottom: '10px' }}>Signos Vitales</div>
          <div className={styles.vitalsGrid}>
            {[
              { f: 'weight', l: 'Peso', u: 'kg', icon: <Icon.ArrowUp s={10} /> },
              { f: 'temperature', l: 'Temp.', u: '°C', icon: <Icon.Paw s={10} /> },
              { f: 'heart_rate', l: 'FC', u: 'bpm', icon: <Icon.Heart s={10} /> },
              { f: 'respiratory_rate', l: 'FR', u: 'rpm', icon: <Icon.Activity s={10} /> },
            ].map(v => (
              <div key={v.f} className={styles.vitalItem}>
                <div className={styles.vitalLabel}>{v.icon} {v.l}</div>
                <div className={styles.vitalWrap}>
                  <input
                    type="number"
                    className={`${styles.vitalValue} ${formErrors[v.f] ? styles.fieldError : ''}`}
                    value={draft[v.f]}
                    onChange={e => {
                      setDraft(d => ({ ...d, [v.f]: e.target.value }));
                      if (formErrors[v.f]) setFormErrors(prev => ({ ...prev, [v.f]: undefined }));
                    }}
                    placeholder="—"
                  />
                  <span className={styles.vitalUnit}>{v.u}</span>
                </div>
                {formErrors[v.f] && (
                  <div className={styles.fieldErrorMessage} style={{ fontSize: '10px', marginTop: '2px' }}>
                    {formErrors[v.f][0]}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className={styles.sidebarSection} style={{ marginTop: 'auto' }}>
          <div style={{ fontSize: '11px', color: '#aaa', textTransform: 'uppercase', fontWeight: '700', letterSpacing: '0.05em', marginBottom: '10px' }}>Resumen</div>
          <div className={styles.resumenCard}>
            <div className={styles.resumenRow}>
              <span>Tipo</span>
              <span className="badge badge-success" style={{ textTransform: 'uppercase', fontSize: '10px' }}>{draft.consultation_type}</span>
            </div>
            <div className={styles.resumenRow}>
              <span>Productos</span>
              <span style={{ fontWeight: '600' }}>{addedProducts.length} ítems</span>
            </div>
            <div className={styles.resumenRow}>
              <span>Servicios</span>
              <span style={{ fontWeight: '600' }}>{addedServices.length}</span>
            </div>
            <div className={`${styles.resumenRow} ${styles.subtotalHighlight}`}>
              <span>Subtotal</span>
              <span>${totalBilling.total.toFixed(2)}</span>
            </div>
          </div>
        </section>
      </aside>
    </div>
  );
}
