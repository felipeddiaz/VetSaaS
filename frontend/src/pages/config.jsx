import { useEffect, useState } from "react";
import { getServices, createService, updateService, deleteService } from "../api/billing";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";

const EMPTY_SERVICE = { name: "", description: "", base_price: "", is_active: true };

const Config = () => {
    const { token, user, initializing } = useAuth();
    const [services, setServices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingService, setEditingService] = useState(null);
    const [form, setForm] = useState(EMPTY_SERVICE);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    useEffect(() => {
        if (token) loadServices();
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

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");
        if (!form.name.trim()) { setError("El nombre es obligatorio"); return; }
        if (!form.base_price || Number(form.base_price) < 0) { setError("El precio es obligatorio"); return; }
        try {
            if (editingService) {
                await updateService(editingService.id, form);
                setSuccess("Servicio actualizado");
            } else {
                await createService(form);
                setSuccess("Servicio creado");
            }
            loadServices();
            closeModal();
        } catch (err) {
            setError(err.response?.data?.error || "Error al guardar");
        }
    };

    const handleDelete = async (id) => {
        if (!confirm("¿Eliminar este servicio?")) return;
        try {
            await deleteService(id);
            setSuccess("Servicio eliminado");
            loadServices();
        } catch (err) {
            setError("No se puede eliminar: puede estar en uso en facturas");
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
        setError("");
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

            {error && (
                <div className="alert alert-danger">
                    {error}
                    <button className="alert-close" onClick={() => setError("")}><Icon.X s={14} /></button>
                </div>
            )}
            {success && (
                <div className="alert alert-success">
                    {success}
                    <button className="alert-close" onClick={() => setSuccess("")}><Icon.X s={14} /></button>
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
                                {error && <div className="alert alert-danger">{error}</div>}

                                <div className="form-group">
                                    <label className="form-label">NOMBRE *</label>
                                    <input
                                        className="input"
                                        value={form.name}
                                        onChange={e => setForm({ ...form, name: e.target.value })}
                                        placeholder="Ej: Consulta general"
                                    />
                                </div>

                                <div className="form-group">
                                    <label className="form-label">PRECIO BASE *</label>
                                    <input
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
                                    <label className="form-label">DESCRIPCIÓN</label>
                                    <textarea
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
