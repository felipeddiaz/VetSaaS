import { useEffect, useState } from "react";
import { getServices, createService, updateService, deleteService } from "../api/billing";
import { getOrgSettings, updateOrgSettings } from "../api/organizations";
import { apiError } from "../utils/apiError";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import { toast } from "sonner";

const EMPTY_SERVICE = { name: "", description: "", base_price: "", is_active: true };

const FLOW_TOGGLES = [
    {
        key: "auto_create_invoice_on_done",
        label: "Crear factura automática al completar cita",
        description: "Al marcar una cita como completada, se genera una factura en borrador automáticamente.",
    },
    {
        key: "require_confirmation_before_start",
        label: "Requerir confirmación antes de iniciar consulta",
        description: "No se puede pasar a 'En consulta' sin pasar primero por 'Confirmada'.",
    },
    {
        key: "auto_create_medical_record",
        label: "Crear historial clínico automático al completar cita",
        description: "Al completar una cita, se abre un historial clínico vacío listo para que el veterinario lo llene.",
    },
    {
        key: "allow_anonymous_walkin",
        label: "Permitir walk-in sin mascota registrada",
        description: "Permite registrar una consulta sin seleccionar mascota, usando el paciente anónimo genérico.",
    },
    {
        key: "show_status_change_history",
        label: "Mostrar historial de cambios de estado en citas",
        description: "Muestra un registro de cada cambio de estado en el detalle de la cita.",
    },
];

const Config = () => {
    const { token, user, initializing } = useAuth();
    const [services, setServices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingService, setEditingService] = useState(null);
    const [form, setForm] = useState(EMPTY_SERVICE);

    const [orgSettings, setOrgSettings] = useState(null);
    const [savingToggle, setSavingToggle] = useState(null);

    useEffect(() => {
        if (token) {
            loadServices();
            getOrgSettings().then(setOrgSettings).catch(err => console.error('[Config] OrgSettings error:', err?.response?.status, err?.response?.data));
        }
    }, [token]);

    const loadServices = async () => {
        setLoading(true);
        try {
            const data = await getServices();
            setServices(data);
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = async (key, value) => {
        setSavingToggle(key);
        try {
            const updated = await updateOrgSettings({ [key]: value });
            setOrgSettings(updated);
            toast.success("Configuración guardada");
        } catch {
            toast.error("Error al guardar configuración");
        } finally {
            setSavingToggle(null);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        const normalizedName = form.name.trim().replace(/\b\w/g, c => c.toUpperCase());
        if (!normalizedName) { toast.error("El nombre es obligatorio"); return; }
        if (!form.base_price || Number(form.base_price) < 0) { toast.error("El precio es obligatorio"); return; }
        const form_ = { ...form, name: normalizedName };
        try {
            const p = editingService ? updateService(editingService.id, form_) : createService(form_);
            await toast.promise(p, {
                loading: editingService ? 'Actualizando...' : 'Creando...',
                success: editingService ? 'Servicio actualizado' : 'Servicio creado',
                error: (err) => apiError(err, "Error al guardar"),
            });
            loadServices();
            closeModal();
        } catch (err) {
        }
    };

    const handleDelete = async (id) => {
        if (!confirm("¿Eliminar este servicio?")) return;
        try {
            await toast.promise(deleteService(id), {
                loading: 'Eliminando...',
                success: 'Servicio eliminado',
                error: 'No se puede eliminar: puede estar en uso en facturas'
            });
            loadServices();
        } catch (err) {
        }
    };

    const openEdit = (svc) => {
        setEditingService(svc);
        setForm({ name: svc.name, description: svc.description || "", base_price: svc.base_price, is_active: svc.is_active });
        setShowModal(true);
    };

    const closeModal = () => {
        setShowModal(false);
        setEditingService(null);
        setForm(EMPTY_SERVICE);
    };

    const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

    if (initializing || loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
                <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
            </div>
        );
    }

    const canManage = user?.role !== "ASSISTANT";

    return (
        <div>
            <div className="page-header">
                <div>
                    <h1 className="page-title">Configuración</h1>
                    <p className="page-subtitle">Ajustes y catálogos de tu organización</p>
                </div>
            </div>

            {/* Flujo Clínico */}
            {orgSettings !== null && (
                <div className="card" style={{ marginBottom: "20px" }}>
                    <div style={{ marginBottom: "18px" }}>
                        <p style={{ fontWeight: "600", fontSize: "14px", marginBottom: "3px" }}>Flujo Clínico</p>
                        <p style={{ fontSize: "12.5px", color: "var(--c-text-2)" }}>
                            Comportamiento automático de citas y consultas en tu organización
                        </p>
                    </div>
                    <div style={{ display: "grid", gap: "12px" }}>
                        {FLOW_TOGGLES.map(({ key, label, description }) => (
                            <div
                                key={key}
                                style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                                    padding: "12px 14px", border: "1px solid var(--c-border)",
                                    borderRadius: "var(--r-md)",
                                    opacity: savingToggle === key ? 0.6 : 1,
                                    transition: "opacity 0.15s",
                                }}
                            >
                                <div style={{ flex: 1, marginRight: "16px" }}>
                                    <p style={{ fontWeight: "600", fontSize: "13.5px", marginBottom: "2px" }}>{label}</p>
                                    <p style={{ fontSize: "12px", color: "var(--c-text-3)" }}>{description}</p>
                                </div>
                                <label style={{ display: "flex", alignItems: "center", cursor: "pointer", flexShrink: 0 }}>
                                    <input
                                        type="checkbox"
                                        checked={!!orgSettings[key]}
                                        disabled={savingToggle === key || !canManage}
                                        onChange={e => handleToggle(key, e.target.checked)}
                                        style={{ width: "16px", height: "16px", cursor: "pointer" }}
                                    />
                                </label>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Catálogo de Servicios */}
            <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "18px" }}>
                    <div>
                        <p style={{ fontWeight: "600", fontSize: "14px", marginBottom: "3px" }}>Catálogo de Servicios</p>
                        <p style={{ fontSize: "12.5px", color: "var(--c-text-2)" }}>
                            Servicios que puedes agregar al facturar una consulta o venta
                        </p>
                    </div>
                    {canManage && (
                        <button
                            className="btn btn-primary btn-sm"
                            onClick={() => { setEditingService(null); setForm(EMPTY_SERVICE); setShowModal(true); }}
                        >
                            + Nuevo Servicio
                        </button>
                    )}
                </div>

                {services.length === 0 ? (
                    <div className="empty-state" style={{ padding: "32px 20px" }}>
                        <p className="empty-state-title">No hay servicios definidos todavía.</p>
                        <p className="empty-state-sub">Agrega servicios para usarlos en facturas.</p>
                    </div>
                ) : (
                    <div style={{ display: "grid", gap: "8px" }}>
                        {services.map(svc => (
                            <div
                                key={svc.id}
                                style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    padding: "12px 14px", border: "1px solid var(--c-border)",
                                    borderRadius: "var(--r-md)",
                                    background: svc.is_active ? "transparent" : "var(--c-subtle)",
                                }}
                            >
                                <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                                        <span style={{ fontWeight: "600", color: svc.is_active ? "var(--c-text)" : "var(--c-text-3)" }}>
                                            {svc.name}
                                        </span>
                                        {!svc.is_active && <span className="badge badge-default">Inactivo</span>}
                                    </div>
                                    {svc.description && (
                                        <p style={{ fontSize: "12px", color: "var(--c-text-3)", marginTop: "2px" }}>{svc.description}</p>
                                    )}
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                                    <span style={{ fontWeight: "700", color: "var(--c-success-text)", minWidth: "70px", textAlign: "right" }}>
                                        ${formatCurrency(svc.base_price)}
                                    </span>
                                    {canManage && (
                                        <div style={{ display: "flex", gap: "6px" }}>
                                            <button className="btn btn-secondary btn-sm" onClick={() => openEdit(svc)}>Editar</button>
                                            <button className="btn btn-danger btn-sm" onClick={() => handleDelete(svc.id)}>Eliminar</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Modal */}
            {showModal && (
                <div className="modal-overlay">
                    <div className="modal modal-sm">
                        <div className="modal-header">
                            <h3>{editingService ? "Editar Servicio" : "Nuevo Servicio"}</h3>
                            <button className="modal-close" onClick={closeModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            <form onSubmit={handleSubmit}>
                                <div className="form-group">
                                    <label className="form-label" htmlFor="service-name">NOMBRE *</label>
                                    <input
                                        id="service-name"
                                        name="service-name"
                                        className="input"
                                        value={form.name}
                                        onChange={e => setForm({ ...form, name: e.target.value })}
                                        placeholder="Ej: Consulta general"
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label" htmlFor="service-price">PRECIO BASE *</label>
                                    <input
                                        id="service-price"
                                        name="service-price"
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        className="input"
                                        value={form.base_price}
                                        onChange={e => setForm({ ...form, base_price: e.target.value })}
                                        placeholder="0.00"
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="form-label" htmlFor="service-description">DESCRIPCIÓN</label>
                                    <textarea
                                        id="service-description"
                                        name="service-description"
                                        className="textarea-input"
                                        style={{ minHeight: "60px" }}
                                        value={form.description}
                                        onChange={e => setForm({ ...form, description: e.target.value })}
                                        placeholder="Descripción opcional..."
                                    />
                                </div>
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input
                                            id="service-active"
                                            name="service-active"
                                            type="checkbox"
                                            checked={form.is_active}
                                            onChange={e => setForm({ ...form, is_active: e.target.checked })}
                                        />
                                        Activo (visible en facturación)
                                    </label>
                                </div>
                            </form>
                        </div>
                        <div className="modal-footer">
                            <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleSubmit}>
                                {editingService ? "Guardar" : "Crear"}
                            </button>
                            <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeModal}>
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Config;
