import { useEffect, useState } from "react";
import { useConfirm } from "../components/ConfirmDialog";
import {
    getInvoices, getInvoice, createInvoice, updateInvoice,
    confirmInvoice, payInvoice,
    addInvoiceItem, deleteInvoiceItem,
    getServices, createService, updateService, deleteService,
} from "../api/billing";
import { getProducts, getPresentations } from "../api/inventory";
import { getPets, getOwners } from "../api/pets";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";

const STATUS_BADGE = { draft: "badge-default", confirmed: "badge-info", paid: "badge-success" };
const STATUS_LABELS = { draft: "Borrador", confirmed: "Confirmada", paid: "Pagada" };

const PAYMENT_METHODS = [
    { value: "cash", label: "Efectivo" },
    { value: "card", label: "Tarjeta" },
    { value: "transfer", label: "Transferencia" },
    { value: "other", label: "Otro" },
];

const EMPTY_SERVICE = { name: "", description: "", base_price: "", is_active: true };
const EMPTY_ITEM = {
    service: "",
    presentation: "",
    quantity: "1",
    discount_type: "",
    discount_value: "",
};

const Billing = () => {
    const { token, user, initializing } = useAuth();
    const confirm = useConfirm();
    const [loading, setLoading] = useState(true);

    const [invoices, setInvoices] = useState([]);
    const [services, setServices] = useState([]);
    const [products, setProducts] = useState([]);
    const [presentations, setPresentations] = useState([]);
    const [pets, setPets] = useState([]);

    const [filterStatus, setFilterStatus] = useState("");
    const [selectedInvoice, setSelectedInvoice] = useState(null);
    const [showDetailModal, setShowDetailModal] = useState(false);
    const [showPayModal, setShowPayModal] = useState(false);
    const [payMethod, setPayMethod] = useState("cash");

    const [showServiceModal, setShowServiceModal] = useState(false);
    const [editingService, setEditingService] = useState(null);
    const [serviceForm, setServiceForm] = useState(EMPTY_SERVICE);

    const [itemForm, setItemForm] = useState(EMPTY_ITEM);
    const [itemMode, setItemMode] = useState(null); // null | "service" | "product"

    const [showNewInvoiceModal, setShowNewInvoiceModal] = useState(false);
    const [newInvoiceForm, setNewInvoiceForm] = useState({
        owner: "",
        pet: "",
        invoice_type: "direct_sale",
    });
    const [owners, setOwners] = useState([]);

    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    useEffect(() => {
        if (token) loadAll();
    }, [token]);

    useEffect(() => {
        loadInvoices();
    }, [filterStatus]);

    useEffect(() => {
        getPresentations({ active: "true" }).then(r => setPresentations(r));
    }, []);

    const loadAll = async () => {
        setLoading(true);
        try {
            const [srvs, prods, petsData, ownersData] = await Promise.all([
                getServices(),
                getProducts({ active: "true" }),
                getPets(token),
                getOwners(),
            ]);
            setServices(srvs);
            setProducts(prods);
            setPets(petsData);
            setOwners(ownersData);
            await loadInvoices();
        } catch (err) {
            console.log(err);
        } finally {
            setLoading(false);
        }
    };

    const loadInvoices = async () => {
        try {
            const params = {};
            if (filterStatus) params.status = filterStatus;
            const data = await getInvoices(params);
            setInvoices(data);
        } catch (err) {
            console.log(err);
        }
    };

    const openInvoiceDetail = async (invoice) => {
        try {
            const detail = await getInvoice(invoice.id);
            setSelectedInvoice(detail);
            setShowDetailModal(true);
            setItemMode(null);
            setItemForm(EMPTY_ITEM);
            setError("");
        } catch (err) {
            setError("Error al cargar la factura");
        }
    };

    const handleConfirm = async () => {
        try {
            const updated = await confirmInvoice(selectedInvoice.id);
            setSelectedInvoice(updated);
            setSuccess("Factura confirmada");
            loadInvoices();
        } catch (err) {
            const errors = err.response?.data?.detail;
            if (Array.isArray(errors)) {
                setError(errors.join("; "));
            } else {
                setError(err.response?.data?.error || "Error al confirmar");
            }
        }
    };

    const handlePay = async () => {
        try {
            const updated = await payInvoice(selectedInvoice.id, payMethod);
            setSelectedInvoice(updated);
            setShowPayModal(false);
            setSuccess("Pago registrado");
            loadInvoices();
        } catch (err) {
            setError(err.response?.data?.error || "Error al registrar pago");
        }
    };

    const handleAddItem = async (e) => {
        e.preventDefault();
        setError("");

        const hasService = Boolean(itemForm.service);
        const hasPresentation = Boolean(itemForm.presentation);

        if (!hasService && !hasPresentation) {
            setError("Selecciona un servicio o una presentación");
            return;
        }

        const payload = {
            service: hasService ? parseInt(itemForm.service) : null,
            presentation: hasPresentation ? parseInt(itemForm.presentation) : null,
            quantity: itemForm.quantity,
            ...(itemForm.discount_type && {
                discount_type: itemForm.discount_type,
                discount_value: itemForm.discount_value || "0",
            }),
        };

        try {
            await addInvoiceItem(selectedInvoice.id, payload);
            const updated = await getInvoice(selectedInvoice.id);
            setSelectedInvoice(updated);
            setItemForm(EMPTY_ITEM);
            setItemMode(null);
            loadInvoices();
        } catch (err) {
            const detail = err.response?.data;
            if (Array.isArray(detail)) {
                setError(detail.join("; "));
            } else if (typeof detail === 'object') {
                setError(Object.values(detail).flat().join("; "));
            } else {
                setError("Error al agregar ítem");
            }
        }
    };

    const handleDeleteItem = async (itemId) => {
        const ok = await confirm({ message: "¿Eliminar este ítem de la factura?", confirmText: "Eliminar", dangerMode: true });
        if (!ok) return;
        try {
            await deleteInvoiceItem(selectedInvoice.id, itemId);
            const updated = await getInvoice(selectedInvoice.id);
            setSelectedInvoice(updated);
            loadInvoices();
        } catch (err) {
            setError("Error al eliminar ítem");
        }
    };

    const handleTaxRateChange = async (taxRate) => {
        try {
            await updateInvoice(selectedInvoice.id, { tax_rate: taxRate });
            const updated = await getInvoice(selectedInvoice.id);
            setSelectedInvoice(updated);
            loadInvoices();
        } catch (err) {
            console.log(err);
        }
    };

    const handleServiceSubmit = async (e) => {
        e.preventDefault();
        setError("");
        if (!serviceForm.name.trim()) { setError("El nombre es obligatorio"); return; }
        if (!serviceForm.base_price || Number(serviceForm.base_price) < 0) { setError("El precio es obligatorio"); return; }
        try {
            if (editingService) {
                await updateService(editingService.id, serviceForm);
                setSuccess("Servicio actualizado");
            } else {
                await createService(serviceForm);
                setSuccess("Servicio creado");
            }
            const srvs = await getServices();
            setServices(srvs);
            closeServiceModal();
        } catch (err) {
            setError(err.response?.data?.error || "Error al guardar");
        }
    };

    const handleDeleteService = async (id) => {
        const ok = await confirm({ message: "¿Eliminar este servicio del catálogo?", confirmText: "Eliminar", dangerMode: true });
        if (!ok) return;
        try {
            await deleteService(id);
            setSuccess("Servicio eliminado");
            const srvs = await getServices();
            setServices(srvs);
        } catch (err) {
            setError("Error al eliminar");
        }
    };

    const onServiceSelect = (serviceId) => {
        const svc = services.find(s => s.id === parseInt(serviceId));
        if (svc) {
            setItemForm({ ...itemForm, service: serviceId, description: svc.name, unit_price: svc.base_price });
        } else {
            setItemForm({ ...itemForm, service: "" });
        }
    };

    const closeServiceModal = () => {
        setShowServiceModal(false);
        setEditingService(null);
        setServiceForm(EMPTY_SERVICE);
        setError("");
    };

    const closeDetailModal = () => {
        setShowDetailModal(false);
        setSelectedInvoice(null);
        setItemMode(null);
        setError("");
    };

    const formatDate = (dateString) => {
        if (!dateString) return "—";
        return new Date(dateString).toLocaleDateString("es-ES", { year: "numeric", month: "short", day: "numeric" });
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
                <h1 className="page-title">Cobros</h1>
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

            {/* Header with filter and new invoice button */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", gap: "20px", flexWrap: "wrap" }}>
                <div>
                    <select
                        className="select-input"
                        value={filterStatus}
                        onChange={e => setFilterStatus(e.target.value)}
                        style={{ maxWidth: "200px" }}
                    >
                        <option value="">Todos los estados</option>
                        {Object.entries(STATUS_LABELS).map(([v, l]) => (
                            <option key={v} value={v}>{l}</option>
                        ))}
                    </select>
                </div>
                {canManage && (
                    <button
                        className="btn btn-primary"
                        onClick={() => {
                            setNewInvoiceForm({ owner: "", pet: "", invoice_type: "direct_sale" });
                            setShowNewInvoiceModal(true);
                        }}
                    >
                        + Nuevo Cobro
                    </button>
                )}
            </div>

            {invoices.length === 0 ? (
                <div className="empty-state">
                    <p className="empty-state-title">No hay cobros registrados</p>
                    <p className="empty-state-sub">Las facturas se generan automáticamente al completar una cita</p>
                </div>
            ) : (
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Mascota · Dueño</th>
                                <th>Tipo</th>
                                <th>Estado</th>
                                <th>Fecha</th>
                                <th style={{ textAlign: "right" }}>Total</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {invoices.map(inv => (
                                <tr key={inv.id}>
                                    <td style={{ color: "var(--c-text-3)", fontWeight: "600" }}>#{inv.id}</td>
                                    <td>
                                        <span style={{ fontWeight: "600" }}>{inv.pet_name}</span>
                                        <span style={{ display: "block", fontSize: "12px", color: "var(--c-text-3)" }}>{inv.owner_name}</span>
                                    </td>
                                    <td>
                                        {inv.invoice_type === "direct_sale" && <span className="badge badge-default">Venta directa</span>}
                                        {inv.invoice_type === "consultation" && <span className="badge badge-info">Consulta</span>}
                                    </td>
                                    <td>
                                        <span className={`badge ${STATUS_BADGE[inv.status]}`}>
                                            {STATUS_LABELS[inv.status]}
                                        </span>
                                    </td>
                                    <td style={{ color: "var(--c-text-3)" }}>{formatDate(inv.created_at)}</td>
                                    <td style={{ textAlign: "right", fontWeight: "700" }}>
                                        ${formatCurrency(inv.total)}
                                    </td>
                                    <td>
                                        <button
                                            className="btn btn-info btn-sm"
                                            onClick={() => openInvoiceDetail(inv)}
                                        >
                                            Ver
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Invoice Detail Modal */}
            {showDetailModal && selectedInvoice && (
                <div className="modal-overlay">
                    <div className="modal modal-lg">
                        <div className="modal-header">
                            <div>
                                <h3>Cobro #{selectedInvoice.id}</h3>
                                <div style={{ display: "flex", gap: "6px", marginTop: "6px", alignItems: "center" }}>
                                    <span className={`badge ${STATUS_BADGE[selectedInvoice.status]}`}>
                                        {STATUS_LABELS[selectedInvoice.status]}
                                    </span>
                                    {selectedInvoice.invoice_type === "direct_sale" && (
                                        <span className="badge badge-default">Venta directa</span>
                                    )}
                                    {selectedInvoice.invoice_type === "consultation" && (
                                        <span className="badge badge-info">Consulta</span>
                                    )}
                                </div>
                            </div>
                            <button className="modal-close" onClick={closeDetailModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            {error && <div className="alert alert-danger">{error}</div>}

                            {/* Patient info */}
                            <div style={{
                                display: "flex", gap: "20px", flexWrap: "wrap",
                                background: "var(--c-subtle)", padding: "14px", borderRadius: "var(--r-lg)",
                                marginBottom: "20px",
                            }}>
                                {[
                                    ["Mascota", selectedInvoice.pet_name],
                                    ["Dueño", selectedInvoice.owner_name],
                                    ["Fecha", formatDate(selectedInvoice.created_at)],
                                    ...(selectedInvoice.status === "paid"
                                        ? [["Pago", PAYMENT_METHODS.find(m => m.value === selectedInvoice.payment_method)?.label || selectedInvoice.payment_method]]
                                        : []),
                                ].map(([label, val]) => (
                                    <div key={label}>
                                        <p style={{ fontSize: "11px", color: "var(--c-text-3)", marginBottom: "2px" }}>{label}</p>
                                        <p style={{ fontWeight: "600", fontSize: "13.5px" }}>{val}</p>
                                    </div>
                                ))}
                            </div>

                            {/* Items */}
                            <div style={{ marginBottom: "16px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                                    <p style={{ fontWeight: "600", fontSize: "13px" }}>Ítems</p>
                                </div>

                                {selectedInvoice.items.length === 0 ? (
                                    <p style={{ color: "var(--c-text-3)", fontSize: "13px", textAlign: "center", padding: "12px" }}>Sin ítems. Agrega servicios o productos.</p>
                                ) : (
                                    <div className="table-wrap" style={{ marginBottom: "0" }}>
                                        <table className="table">
                                            <thead>
                                                <tr>
                                                    <th>Descripción</th>
                                                    <th>Cant.</th>
                                                    <th>P. Unit.</th>
                                                    <th>Descuento</th>
                                                    <th>Subtotal</th>
                                                    <th></th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {selectedInvoice.items.map(item => (
                                                    <tr key={item.id}>
                                                        <td>{item.description}</td>
                                                        <td>{item.quantity}</td>
                                                        <td>${formatCurrency(item.unit_price)}</td>
                                                        <td style={{ color: "var(--c-text-3)", fontSize: "12px" }}>
                                                            {item.discount_type === "percentage" && `${item.discount_value}%`}
                                                            {item.discount_type === "fixed" && `-$${formatCurrency(item.discount_value)}`}
                                                            {!item.discount_type && "—"}
                                                        </td>
                                                        <td style={{ fontWeight: "600" }}>${formatCurrency(item.subtotal)}</td>
                                                        <td>
                                                            {canManage && selectedInvoice.status === "draft" && (
                                                                <button
                                                                    className="btn btn-danger btn-xs"
                                                                    onClick={() => handleDeleteItem(item.id)}
                                                                >
                                                                    <Icon.X s={11} />
                                                                </button>
                                                            )}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}

                                {/* Botones Agregar Servicio / Producto */}
                                {canManage && selectedInvoice.status === "draft" && (
                                    <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            style={{ flex: 1 }}
                                            onClick={() => setItemMode(itemMode === "service" ? null : "service")}
                                        >
                                            + Agregar Servicio
                                        </button>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            style={{ flex: 1 }}
                                            onClick={() => setItemMode(itemMode === "product" ? null : "product")}
                                        >
                                            + Agregar Producto
                                        </button>
                                    </div>
                                )}

                                {/* Sub-formulario SERVICIO */}
                                {itemMode === "service" && selectedInvoice.status === "draft" && (
                                    <form
                                        onSubmit={handleAddItem}
                                        style={{
                                            background: "var(--c-subtle)", padding: "14px",
                                            borderRadius: "var(--r-lg)", marginTop: "12px",
                                            border: "1px solid var(--c-border)",
                                        }}
                                    >
                                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
                                            <div>
                                                <label className="form-label">SERVICIO *</label>
                                                <select
                                                    className="select-input"
                                                    value={itemForm.service}
                                                    onChange={e => setItemForm(f => ({ ...f, service: e.target.value, presentation: "" }))}
                                                    required
                                                >
                                                    <option value="">— Seleccionar servicio —</option>
                                                    {services.filter(s => s.is_active).map(s => (
                                                        <option key={s.id} value={s.id}>
                                                            {s.name} — ${formatCurrency(s.base_price)}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="form-label">CANTIDAD</label>
                                                <input
                                                    type="number" min="0.01" step="0.01" className="input"
                                                    value={itemForm.quantity}
                                                    onChange={e => setItemForm(f => ({ ...f, quantity: e.target.value }))}
                                                />
                                            </div>
                                            <div>
                                                <label className="form-label">DESCUENTO (opcional)</label>
                                                <select
                                                    className="select-input"
                                                    value={itemForm.discount_type}
                                                    onChange={e => setItemForm(f => ({ ...f, discount_type: e.target.value, discount_value: "" }))}
                                                >
                                                    <option value="">Sin descuento</option>
                                                    <option value="percentage">Porcentaje (%)</option>
                                                    <option value="fixed">Monto fijo ($)</option>
                                                </select>
                                            </div>
                                            {itemForm.discount_type && (
                                                <div>
                                                    <label className="form-label">
                                                        {itemForm.discount_type === "percentage" ? "PORCENTAJE" : "MONTO A DESCONTAR"}
                                                    </label>
                                                    <input
                                                        type="number" min="0.01" step="0.01" className="input"
                                                        value={itemForm.discount_value}
                                                        onChange={e => setItemForm(f => ({ ...f, discount_value: e.target.value }))}
                                                        placeholder={itemForm.discount_type === "percentage" ? "ej: 10" : "ej: 50.00"}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                        {itemForm.service && (
                                            <div style={{
                                                gridColumn: "1 / -1",
                                                background: "var(--c-surface)",
                                                borderRadius: "var(--r-md)",
                                                padding: "10px 14px",
                                                fontSize: "12.5px",
                                                color: "var(--c-text-2)",
                                                marginBottom: "10px",
                                            }}>
                                                {(() => {
                                                    const svc = services.find(s => s.id === parseInt(itemForm.service));
                                                    if (!svc) return null;
                                                    const qty = Number(itemForm.quantity) || 1;
                                                    const gross = svc.base_price * qty;
                                                    let discount = 0;
                                                    if (itemForm.discount_type === "percentage") {
                                                        discount = gross * (Number(itemForm.discount_value) / 100);
                                                    } else if (itemForm.discount_type === "fixed") {
                                                        discount = Math.min(Number(itemForm.discount_value) || 0, gross);
                                                    }
                                                    const net = gross - discount;
                                                    return (
                                                        <>
                                                            <span>Precio unitario: <strong>${formatCurrency(svc.base_price)}</strong></span>
                                                            {discount > 0 && (
                                                                <span style={{ marginLeft: "12px", color: "var(--c-warning-text)" }}>
                                                                    Descuento: -${formatCurrency(discount)}
                                                                </span>
                                                            )}
                                                            <span style={{ marginLeft: "12px", fontWeight: "700", color: "var(--c-success-text)" }}>
                                                                Total línea: ${formatCurrency(net)}
                                                            </span>
                                                        </>
                                                    );
                                                })()}
                                            </div>
                                        )}
                                        <div style={{ display: "flex", gap: "8px" }}>
                                            <button type="submit" className="btn btn-primary btn-sm">Agregar</button>
                                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setItemMode(null); setItemForm(EMPTY_ITEM); }}>Cancelar</button>
                                        </div>
                                    </form>
                                )}

                                {/* Sub-formulario PRODUCTO */}
                                {itemMode === "product" && selectedInvoice.status === "draft" && (
                                    <form
                                        onSubmit={handleAddItem}
                                        style={{
                                            background: "var(--c-subtle)", padding: "14px",
                                            borderRadius: "var(--r-lg)", marginTop: "12px",
                                            border: "1px solid var(--c-border)",
                                        }}
                                    >
                                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
                                            <div>
                                                <label className="form-label">PRESENTACIÓN *</label>
                                                <select
                                                    className="select-input"
                                                    value={itemForm.presentation}
                                                    onChange={e => setItemForm(f => ({ ...f, presentation: e.target.value, service: "" }))}
                                                    required
                                                >
                                                    <option value="">— Seleccionar producto —</option>
                                                    {presentations.map(p => (
                                                        <option key={p.id} value={p.id} disabled={p.stock <= 0}>
                                                            {p.product_name} — {p.name}
                                                            {p.stock <= 0 ? ' (sin stock)' : ` ($${formatCurrency(p.sale_price)} | stock: ${p.stock})`}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="form-label">CANTIDAD</label>
                                                <input
                                                    type="number" min="0.01" step="0.01" className="input"
                                                    value={itemForm.quantity}
                                                    onChange={e => setItemForm(f => ({ ...f, quantity: e.target.value }))}
                                                />
                                            </div>
                                            <div>
                                                <label className="form-label">DESCUENTO (opcional)</label>
                                                <select
                                                    className="select-input"
                                                    value={itemForm.discount_type}
                                                    onChange={e => setItemForm(f => ({ ...f, discount_type: e.target.value, discount_value: "" }))}
                                                >
                                                    <option value="">Sin descuento</option>
                                                    <option value="percentage">Porcentaje (%)</option>
                                                    <option value="fixed">Monto fijo ($)</option>
                                                </select>
                                            </div>
                                            {itemForm.discount_type && (
                                                <div>
                                                    <label className="form-label">
                                                        {itemForm.discount_type === "percentage" ? "PORCENTAJE" : "MONTO A DESCONTAR"}
                                                    </label>
                                                    <input
                                                        type="number" min="0.01" step="0.01" className="input"
                                                        value={itemForm.discount_value}
                                                        onChange={e => setItemForm(f => ({ ...f, discount_value: e.target.value }))}
                                                        placeholder={itemForm.discount_type === "percentage" ? "ej: 10" : "ej: 50.00"}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                        {itemForm.presentation && (
                                            <div style={{
                                                gridColumn: "1 / -1",
                                                background: "var(--c-surface)",
                                                borderRadius: "var(--r-md)",
                                                padding: "10px 14px",
                                                fontSize: "12.5px",
                                                color: "var(--c-text-2)",
                                                marginBottom: "10px",
                                            }}>
                                                {(() => {
                                                    const pres = presentations.find(p => p.id === parseInt(itemForm.presentation));
                                                    if (!pres) return null;
                                                    const qty = Number(itemForm.quantity) || 1;
                                                    const gross = pres.sale_price * qty;
                                                    let discount = 0;
                                                    if (itemForm.discount_type === "percentage") {
                                                        discount = gross * (Number(itemForm.discount_value) / 100);
                                                    } else if (itemForm.discount_type === "fixed") {
                                                        discount = Math.min(Number(itemForm.discount_value) || 0, gross);
                                                    }
                                                    const net = gross - discount;
                                                    return (
                                                        <>
                                                            <span>Precio unitario: <strong>${formatCurrency(pres.sale_price)}</strong></span>
                                                            {discount > 0 && (
                                                                <span style={{ marginLeft: "12px", color: "var(--c-warning-text)" }}>
                                                                    Descuento: -${formatCurrency(discount)}
                                                                </span>
                                                            )}
                                                            <span style={{ marginLeft: "12px", fontWeight: "700", color: "var(--c-success-text)" }}>
                                                                Total línea: ${formatCurrency(net)}
                                                            </span>
                                                        </>
                                                    );
                                                })()}
                                            </div>
                                        )}
                                        <div style={{ display: "flex", gap: "8px" }}>
                                            <button type="submit" className="btn btn-primary btn-sm">Agregar</button>
                                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setItemMode(null); setItemForm(EMPTY_ITEM); }}>Cancelar</button>
                                        </div>
                                    </form>
                                )}
                            </div>

                            {/* Totals */}
                            <div style={{ borderTop: "1px solid var(--c-border)", paddingTop: "14px", marginBottom: "8px" }}>
                                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                                    <div style={{ minWidth: "220px" }}>
                                        {[
                                            ["Subtotal", `$${formatCurrency(selectedInvoice.subtotal)}`],
                                            [`IVA (${(Number(selectedInvoice.tax_rate) * 100).toFixed(0)}%)`, `$${formatCurrency(selectedInvoice.tax_amount)}`],
                                        ].map(([label, value]) => (
                                            <div key={label} style={{ display: "flex", justifyContent: "space-between", marginBottom: "5px" }}>
                                                <span style={{ color: "var(--c-text-2)", fontSize: "13px" }}>{label}</span>
                                                <span style={{ fontSize: "13px" }}>{value}</span>
                                            </div>
                                        ))}
                                        <div style={{
                                            display: "flex", justifyContent: "space-between",
                                            fontWeight: "700", fontSize: "16px",
                                            borderTop: "1px solid var(--c-border)", paddingTop: "8px", marginTop: "6px",
                                        }}>
                                            <span>Total</span>
                                            <span style={{ color: "var(--c-success-text)" }}>${formatCurrency(selectedInvoice.total)}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Actions */}
                        {canManage && (
                            <div className="modal-footer">
                                {selectedInvoice.status === "draft" && (
                                    <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleConfirm}>
                                        Continuar al pago
                                    </button>
                                )}
                                {selectedInvoice.status === "confirmed" && (
                                    <button
                                        className="btn btn-primary btn-md"
                                        style={{ flex: 1, background: "#059669", borderColor: "#059669" }}
                                        onClick={() => setShowPayModal(true)}
                                    >
                                        Registrar Pago
                                    </button>
                                )}
                                <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeDetailModal}>
                                    Cerrar
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Pay Modal */}
            {showPayModal && (
                <div className="modal-overlay" style={{ zIndex: 1100 }}>
                    <div className="modal modal-sm">
                        <div className="modal-header">
                            <h3>Registrar Pago</h3>
                            <button className="modal-close" onClick={() => setShowPayModal(false)}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            <div className="form-group">
                                <label className="form-label">MÉTODO DE PAGO</label>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                                    {PAYMENT_METHODS.map(m => (
                                        <button
                                            key={m.value}
                                            type="button"
                                            onClick={() => setPayMethod(m.value)}
                                            className={`btn btn-md${payMethod === m.value ? " btn-primary" : " btn-secondary"}`}
                                        >
                                            {m.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <p style={{ fontSize: "13px", color: "var(--c-text-2)" }}>
                                Total a cobrar:{" "}
                                <strong style={{ color: "var(--c-success-text)", fontSize: "16px" }}>
                                    ${formatCurrency(selectedInvoice?.total)}
                                </strong>
                            </p>
                        </div>
                        <div className="modal-footer">
                            <button
                                className="btn btn-md"
                                style={{ flex: 1, background: "#059669", borderColor: "#059669", color: "#fff" }}
                                onClick={handlePay}
                            >
                                Confirmar Pago
                            </button>
                            <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={() => setShowPayModal(false)}>
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* New Invoice Modal */}
            {showNewInvoiceModal && (
                <div className="modal-overlay">
                    <div className="modal modal-lg">
                        <div className="modal-header">
                            <h3>Nuevo Cobro</h3>
                            <button className="modal-close" onClick={() => setShowNewInvoiceModal(false)}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            {error && <div className="alert alert-danger">{error}</div>}

                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "20px" }}>
                                <div>
                                    <label className="label">Propietario</label>
                                    <select
                                        className="input"
                                        value={newInvoiceForm.owner}
                                        onChange={e => setNewInvoiceForm(f => ({ ...f, owner: e.target.value }))}
                                    >
                                        <option value="">— Seleccionar propietario —</option>
                                        {owners.map(o => (
                                            <option key={o.id} value={o.id}>{o.name}</option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="label">Mascota</label>
                                    <select
                                        className="input"
                                        value={newInvoiceForm.pet}
                                        onChange={e => setNewInvoiceForm(f => ({ ...f, pet: e.target.value }))}
                                        disabled={!newInvoiceForm.owner}
                                    >
                                        <option value="">— Seleccionar mascota —</option>
                                        {pets
                                            .filter(p => {
                                                if (!newInvoiceForm.owner) return true;
                                                return parseInt(p.owner_id) === parseInt(newInvoiceForm.owner);
                                            })
                                            .map(p => (
                                                <option key={p.id} value={p.id}>{p.name}</option>
                                            ))}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label className="label">Tipo de Factura</label>
                                <select
                                    className="input"
                                    value={newInvoiceForm.invoice_type}
                                    onChange={e => setNewInvoiceForm(f => ({ ...f, invoice_type: e.target.value }))}
                                >
                                    <option value="direct_sale">Venta directa</option>
                                    <option value="consultation">Consulta</option>
                                </select>
                            </div>
                        </div>
                        <div className="modal-footer">
                            <button
                                className="btn btn-secondary"
                                onClick={() => setShowNewInvoiceModal(false)}
                            >
                                Cancelar
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={async () => {
                                    try {
                                        setError("");
                                        const newInv = await createInvoice({
                                            owner: parseInt(newInvoiceForm.owner),
                                            pet: parseInt(newInvoiceForm.pet),
                                            invoice_type: newInvoiceForm.invoice_type,
                                        });
                                        setShowNewInvoiceModal(false);
                                        await loadInvoices();
                                        await openInvoiceDetail(newInv);
                                    } catch (err) {
                                        setError(err.response?.data?.detail || "Error al crear factura");
                                    }
                                }}
                            >
                                Crear Factura
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Billing;
