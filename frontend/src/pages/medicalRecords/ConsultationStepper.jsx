import { useEffect, useRef, useState } from "react";
import { Icon } from "../../components/icons";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { useAuth } from "../../auth/authContext";
import {
  createMedicalRecord,
  updateMedicalRecord,
  getMedicalRecord,
  closeMedicalRecord,
} from "../../api/medicalRecords";
import { createVitals } from "../../api/vitals";
import {
  addMedicalRecordProduct,
  removeMedicalRecordProduct,
  getMedicalRecordProducts,
} from "../../api/inventory";
import SearchSelect from "../../components/SearchSelect";
import SidePanel from "./SidePanel";
import styles from "./stepper.module.css";

const CONSULTATION_TYPES = [
  { value: "general", label: "General", desc: "Chequeo, control", icon: <Icon.Paw s={18} /> },
  { value: "vaccine", label: "Vacuna", desc: "Inmunización", icon: <Icon.Syringe s={18} /> },
  { value: "surgery", label: "Cirugía", desc: "Proc. quirúrgico", icon: <Icon.Activity s={18} /> },
  { value: "emergency", label: "Urgencia", desc: "Atención inmediata", icon: <Icon.AlertCircle s={18} /> },
];

const STEPS = [
  { id: 1, label: "Diagnóstico" },
  { id: 2, label: "Tratamiento" },
  { id: 3, label: "Productos" },
  { id: 4, label: "Facturación" },
];

const FIELD_TO_STEP = {
  consultation_type: 1,
  diagnosis: 1,
  notes: 1,
  treatment: 2,
  weight: 2,
};

const INITIAL_DRAFT = {
  consultation_type: "general",
  diagnosis: "",
  treatment: "",
  notes: "",
  weight: "",
  temperature: "",
  heart_rate: "",
  respiratory_rate: "",
};

export default function ConsultationStepper({
  pet,
  products = [],
  productMap = {},
  onClose,
  onComplete,
  initialRecord = null,
}) {
  const { token, user } = useAuth();
  const isEditing = initialRecord && initialRecord.id;
  const [step, setStep] = useState(isEditing ? 1 : 1);
  const [recordId, setRecordId] = useState(isEditing ? initialRecord.id : null);
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
    return { ...INITIAL_DRAFT };
  });
  const [dirtySteps, setDirtySteps] = useState(new Set());
  const [addedProducts, setAddedProducts] = useState([]);
  const [productLine, setProductLine] = useState({ product: "", quantity: "1" });
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [panelRefreshKey, setPanelRefreshKey] = useState(0);
  const overlayRef = useRef(null);
  const productsLoaded = useRef(false);

  useEffect(() => {
    if (isEditing && recordId && !productsLoaded.current) {
      productsLoaded.current = true;
      const loadProducts = async () => {
        try {
          const { getMedicalRecordProducts } = await import("../../api/inventory");
          const data = await getMedicalRecordProducts(recordId);
          const list = Array.isArray(data) ? data : (data?.results || []);
          setAddedProducts(list);
        } catch { }
      };
      loadProducts();
    }
  }, [isEditing, recordId]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose?.();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const markDirty = (stepId) => {
    setDirtySteps((prev) => new Set(prev).add(stepId));
  };

  const toNumberOrNull = (v) => {
    if (v === "" || v == null) return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  };

  const handleSaveError = (err) => {
    const data = err?.response?.data;
    if (data?.errors && typeof data.errors === "object" && !Array.isArray(data.errors)) {
      const mapped = {};
      for (const [field, msgs] of Object.entries(data.errors)) {
        mapped[field] = Array.isArray(msgs) ? msgs[0] : msgs;
      }
      setErrors(mapped);
    }
    const msg = apiError(err, "Error al guardar");
    toast.error(msg);
  };

  const goNext = async (fromStep) => {
    setErrors({});

    if (fromStep === 1 && !recordId) {
      setSaving(true);
      try {
        const result = await createMedicalRecord(token, {
          pet: pet.id,
          consultation_type: draft.consultation_type,
          diagnosis: draft.diagnosis,
          treatment: draft.treatment,
          notes: draft.notes,
          weight: draft.weight || null,
        });
        setRecordId(result.id);
        setDirtySteps((prev) => {
          const n = new Set(prev);
          n.delete(1);
          return n;
        });
        setPanelRefreshKey((k) => k + 1);
        setStep(2);
      } catch (err) {
        handleSaveError(err);
      } finally {
        setSaving(false);
      }
      return;
    }

    if (fromStep === 1 && recordId) {
      if (!dirtySteps.has(1)) { setStep(2); return; }
      setSaving(true);
      try {
        await updateMedicalRecord(token, recordId, {
          pet: pet.id,
          consultation_type: draft.consultation_type,
          diagnosis: draft.diagnosis,
          treatment: draft.treatment,
          notes: draft.notes,
        });
        setDirtySteps((prev) => {
          const n = new Set(prev);
          n.delete(1);
          return n;
        });
        setStep(2);
      } catch (err) {
        handleSaveError(err);
      } finally {
        setSaving(false);
      }
      return;
    }

    if (dirtySteps.has(fromStep) && recordId) {
      setSaving(true);
      try {
        const payload = {
          pet: pet.id,
          consultation_type: draft.consultation_type,
          diagnosis: draft.diagnosis,
          treatment: draft.treatment,
          notes: draft.notes,
        };
        if (fromStep !== 2) {
          payload.weight = toNumberOrNull(draft.weight);
        }
        await updateMedicalRecord(token, recordId, payload);

        if (fromStep === 2) {
          const vitalFields = ["weight", "temperature", "heart_rate", "respiratory_rate"];
          const hasVitals = vitalFields.some(f => draft[f] !== "" && draft[f] != null);
          if (hasVitals) {
            await createVitals(recordId, {
              weight: toNumberOrNull(draft.weight),
              temperature: toNumberOrNull(draft.temperature),
              heart_rate: toNumberOrNull(draft.heart_rate),
              respiratory_rate: toNumberOrNull(draft.respiratory_rate),
            });
          }
        }

        setDirtySteps((prev) => {
          const n = new Set(prev);
          n.delete(fromStep);
          return n;
        });
        setPanelRefreshKey((k) => k + 1);
        setStep(fromStep + 1);
      } catch (err) {
        handleSaveError(err);
      } finally {
        setSaving(false);
      }
      return;
    }

    setStep(fromStep + 1);
  };

  const goBack = (fromStep) => {
    setErrors({});
    setStep(fromStep - 1);
  };

  const handleCloseRecord = async () => {
    setSaving(true);
    setErrors({});
    try {
      await closeMedicalRecord(token, recordId);
      toast.success("Consulta finalizada exitosamente");
      onComplete?.(recordId);
      onClose?.(recordId);
    } catch (err) {
      const data = err?.response?.data;
      if (data?.errors && typeof data.errors === "object" && !Array.isArray(data.errors)) {
        const fields = Object.keys(data.errors);
        let targetStep = 4;
        for (const field of fields) {
          const s = FIELD_TO_STEP[field];
          if (s && s < targetStep) targetStep = s;
        }
        setStep(targetStep);
        const mapped = {};
        for (const field of fields) {
          mapped[field] = Array.isArray(data.errors[field])
            ? data.errors[field][0]
            : data.errors[field];
        }
        setErrors(mapped);
        if (targetStep < 4) {
          markDirty(targetStep);
        }
      }
      const msg = apiError(err, "Error al finalizar la consulta");
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

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

  const handleAddProduct = async () => {
    if (!productLine.product) {
      toast.error("Selecciona un producto");
      return;
    }
    const selected = productMap[productLine.product];
    if (!selected?.presentation?.id) {
      toast.error("El producto no tiene presentación configurada");
      return;
    }
    const qty = Number(productLine.quantity);
    if (!qty || qty <= 0) {
      toast.error("La cantidad debe ser mayor a 0");
      return;
    }
    setSaving(true);
    try {
      const result = await addMedicalRecordProduct(recordId, {
        presentation: selected.presentation.id,
        quantity: productLine.quantity,
      });
      setAddedProducts((prev) => [
        ...prev,
        {
          id: result.id,
          product_id: selected.id,
          product_name: selected.name,
          presentation_name: selected.presentation.name,
          quantity: result.quantity,
          unit_price: result.unit_price,
        },
      ]);
      setProductLine({ product: "", quantity: "1" });
      setPanelRefreshKey((k) => k + 1);
      toast.success("Producto agregado");
    } catch (err) {
      const msg = apiError(err, "Error al agregar producto");
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveProduct = async (productEntryId) => {
    setSaving(true);
    try {
      await removeMedicalRecordProduct(recordId, productEntryId);
      setAddedProducts((prev) => prev.filter((p) => p.id !== productEntryId));
      setPanelRefreshKey((k) => k + 1);
      toast.success("Producto removido");
    } catch (err) {
      const msg = apiError(err, "Error al quitar producto");
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const formatCurrency = (num) => {
    if (num == null) return "$0.00";
    return `\$${Number(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const isStepActive = (stepId) => step === stepId;
  const isStepCompleted = (stepId) => step > stepId;

  const showTreatmentSurgeryWarning =
    step === 2 && draft.consultation_type === "surgery" && !draft.treatment.trim();

  return (
    <div className={styles.stepperOverlay} ref={overlayRef}>
      <div className={styles.stepperContainer}>
        <div className={styles.stepperHeader}>
          <div className={styles.headerLeft}>
            <div className={styles.breadcrumbs}>
              <span>VetCare</span> / <span>Historial Clínico</span>
            </div>
            <div className={styles.headerActions}>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>Cancelar</button>
              <button className="btn btn-secondary btn-sm">Guardar borrador</button>
              <button className={`${styles.btnFinalizar} btn btn-sm`} onClick={handleCloseRecord}>
                <Icon.Check s={14} /> Finalizar
              </button>
            </div>
          </div>
          <button className={styles.stepperClose} onClick={onClose} type="button">
            <Icon.X s={18} />
          </button>
        </div>

        <div className={styles.stepperBar}>
          <div className={styles.stepsList}>
            {STEPS.map((s, i) => (
              <div key={s.id} className={`${styles.stepItem} ${step === s.id ? styles.stepActive : step > s.id ? styles.stepCompleted : ""}`}>
                <div className={styles.stepCircle}>
                  {step > s.id ? <Icon.Check s={12} /> : s.id}
                </div>
                <div className={styles.stepLabel}>
                  <div className={styles.stepLabelText}>{s.label}</div>
                </div>
                {i < STEPS.length - 1 && <div className={styles.stepConnector} />}
              </div>
            ))}
          </div>
          <div className={styles.headerMeta}>
            <span>4 mayo 2026 · 12:23</span>
            <span>Dr. {user?.first_name || "Reynaldo"}</span>
            <span>Sala 2</span>
          </div>
        </div>

        <div className={styles.stepperBody}>
          <div className={styles.stepperForm}>
            {step === 1 && (
              <>
                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionTitle}>Tipo de consulta</h3>
                </div>
                <div className={styles.typeGrid}>
                  {CONSULTATION_TYPES.map(t => (
                    <div key={t.value}
                      className={`${styles.typeCard} ${draft.consultation_type === t.value ? styles.typeCardActive : ""}`}
                      onClick={() => {
                        setDraft(d => ({ ...d, consultation_type: t.value }));
                        markDirty(1);
                      }}
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
                  <h3 className={styles.sectionTitle}>Motivo y diagnóstico</h3>
                </div>

                <div className="form-group">
                  <label className="form-label">Motivo de consulta</label>
                  <textarea
                    className="textarea-input"
                    rows={2}
                    maxLength={100}
                    placeholder="Tos seca persistente"
                    value={draft.notes}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, notes: e.target.value }));
                      markDirty(1);
                    }}
                  />
                  <div className={styles.charCounter}>
                    {draft.notes.length}/100
                  </div>
                  {errors.notes && <div className={styles.fieldError}>{errors.notes}</div>}
                </div>

                <div className="form-group">
                  <label className="form-label">Diagnóstico clínico</label>
                  <textarea
                    className="textarea-input"
                    rows={3}
                    maxLength={400}
                    placeholder="Bronquitis aguda"
                    value={draft.diagnosis}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, diagnosis: e.target.value }));
                      markDirty(1);
                    }}
                  />
                  <div className={styles.charCounter}>
                    {draft.diagnosis.length}/400
                  </div>
                  {errors.diagnosis && <div className={styles.fieldError}>{errors.diagnosis}</div>}
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionTitle}>Tratamiento</h3>
                </div>

                <div className="form-group">
                  <label className="form-label">Indicaciones generales</label>
                  <textarea
                    className="textarea-input"
                    rows={3}
                    maxLength={400}
                    placeholder="Doxiciclina 50mg cada 12h x 7 días"
                    value={draft.treatment}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, treatment: e.target.value }));
                      markDirty(2);
                    }}
                  />
                  <div className={styles.charCounter}>
                    {draft.treatment.length}/400
                  </div>
                  {errors.treatment && <div className={styles.fieldError}>{errors.treatment}</div>}
                </div>

                {showTreatmentSurgeryWarning && (
                  <div className={styles.fieldWarning}>
                    El tratamiento es obligatorio para consultas de tipo cirugía
                  </div>
                )}

                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionTitle}>Ultimos Signos vitales registrados</h3>
                </div>

                <div className={styles.vitalsGrid}>
                  {[
                    { field: "weight", label: "Peso", unit: "kg", icon: <Icon.ArrowUp s={10} /> },
                    { field: "temperature", label: "Temp.", unit: "°C", icon: <Icon.Paw s={10} /> },
                    { field: "heart_rate", label: "FC", unit: "bpm", icon: <Icon.Heart s={10} /> },
                    { field: "respiratory_rate", label: "FR", unit: "rpm", icon: <Icon.Activity s={10} /> },
                  ].map(v => (
                    <div className={styles.vitalItem} key={v.field}>
                      <div className={styles.vitalLabel}>{v.icon} {v.label}</div>
                      <div className={styles.vitalWrap}>
                        <input
                          type="number"
                          className={styles.vitalInput}
                          step="0.01"
                          min="0"
                          placeholder="—"
                          value={draft[v.field]}
                          onChange={(e) => {
                            setDraft((d) => ({ ...d, [v.field]: e.target.value }));
                            markDirty(2);
                          }}
                        />
                        <span className={styles.vitalUnit}>{v.unit}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionTitle}>Productos consumidos</h3>
                </div>

                <div className={styles.productAddRow}>
                  <div className={styles.productSearchCol}>
                    <SearchSelect
                      value={
                        productLine.product
                          ? { id: productLine.product, label: productMap[productLine.product]?.name || "" }
                          : null
                      }
                      onChange={(item) =>
                        setProductLine((pl) => ({ ...pl, product: item ? item.id : "" }))
                      }
                      onSearch={handleProductSearch}
                      placeholder="Buscar producto..."
                      disabled={saving}
                    />
                  </div>
                  <div className={styles.productQtyCol}>
                    <input
                      type="number"
                      className="input"
                      min="0.01"
                      step="0.01"
                      value={productLine.quantity}
                      onChange={(e) =>
                        setProductLine((pl) => ({ ...pl, quantity: e.target.value }))
                      }
                      disabled={saving}
                    />
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={handleAddProduct}
                    disabled={saving || !productLine.product}
                  >
                    Agregar
                  </button>
                </div>

                {addedProducts.length === 0 ? (
                  <p className={styles.emptyState}>Sin productos agregados</p>
                ) : (
                  <div className={styles.productList}>
                    {addedProducts.map((item) => (
                      <div key={item.id} className={styles.productItem}>
                        <div className={styles.productItemInfo}>
                          <span className={styles.productItemName}>{item.product_name}</span>
                          {item.presentation_name && item.presentation_name !== item.product_name && (
                            <span className={styles.productItemPres}>
                              {item.presentation_name}
                            </span>
                          )}
                          <span className={styles.productItemQty}>x{item.quantity}</span>
                          {item.unit_price != null && (
                            <span className={styles.productItemPrice}>
                              {formatCurrency(item.unit_price * item.quantity)}
                            </span>
                          )}
                        </div>
                        <button
                          type="button"
                          className={styles.productRemoveBtn}
                          onClick={() => handleRemoveProduct(item.id)}
                          disabled={saving}
                          title="Quitar producto"
                        >
                          <Icon.Trash s={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {step === 4 && (
              <>
                <div className={styles.sectionHeader}>
                  <h3 className={styles.sectionTitle}>Facturación</h3>
                </div>

                <div className={styles.summarySection}>
                  <div className={styles.summaryLabel}>Diagnóstico</div>
                  <div className={styles.summaryValue}>
                    {draft.diagnosis || (
                      <span style={{ color: "var(--c-text-3)", fontStyle: "italic" }}>
                        Sin diagnóstico
                      </span>
                    )}
                  </div>
                </div>

                <div className={styles.summarySection}>
                  <div className={styles.summaryLabel}>Tratamiento</div>
                  <div className={styles.summaryValue}>
                    {draft.treatment || (
                      <span style={{ color: "var(--c-text-3)", fontStyle: "italic" }}>
                        Sin tratamiento
                      </span>
                    )}
                  </div>
                </div>

                <div className={styles.summarySection}>
                  <div className={styles.summaryLabel}>Tipo de consulta</div>
                  <div className={styles.summaryValue}>
                    <span className="badge badge-purple">
                      {CONSULTATION_TYPES.find((ct) => ct.value === draft.consultation_type)
                        ?.label || draft.consultation_type}
                    </span>
                  </div>
                </div>

                <div className={styles.summarySection}>
                  <div className={styles.summaryLabel}>Productos utilizados</div>
                  {addedProducts.length === 0 ? (
                    <div className={styles.summaryValue} style={{ fontStyle: "italic", color: "var(--c-text-3)" }}>
                      Ninguno
                    </div>
                  ) : (
                    <div className={styles.productList}>
                      {addedProducts.map((item) => (
                        <div key={item.id} className={styles.productItem}>
                          <div className={styles.productItemInfo}>
                            <span className={styles.productItemName}>{item.product_name}</span>
                            <span className={styles.productItemQty}>x{item.quantity}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {errors._close && (
                  <div className={styles.fieldError} style={{ marginTop: 12 }}>
                    {errors._close}
                  </div>
                )}
              </>
            )}
          </div>

          {recordId && (
            <div className={styles.stepperSidebar}>
              <SidePanel
                recordId={recordId}
                pet={pet}
                refreshKey={panelRefreshKey}
                compact={true}
              />
            </div>
          )}
        </div>

        <div className={styles.stepperFooter}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => goBack(step)}
            disabled={step === 1 || saving}
          >
            <Icon.ChevronLeft s={16} /> Anterior
          </button>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn btn-secondary btn-sm">Guardar y cerrar</button>
            {step < 4 ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                style={{ background: '#1a4434' }}
                onClick={() => goNext(step)}
                disabled={saving}
              >
                Siguiente <Icon.ChevronRight s={16} />
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                style={{ background: '#1a4434' }}
                onClick={handleCloseRecord}
                disabled={saving}
              >
                <Icon.Check s={14} /> Guardar y Cerrar
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
