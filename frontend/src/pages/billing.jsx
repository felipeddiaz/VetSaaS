import { useEffect, useState } from "react";
import { useConfirm } from "../components/ConfirmDialog";
import { apiError } from "../utils/apiError";
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
import { toast } from "sonner";
import SearchSelect from "../components/SearchSelect";

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
    const [newInvoiceOwner, setNewInvoiceOwner] = useState(null);
    const [newInvoicePet,   setNewInvoicePet]   = useState(null);
    const [newInvoiceType,  setNewInvoiceType]  = useState("direct_sale");
    const [genericOwner,    setGenericOwner]    = useState(null);

    useEffect(() => {
        if (token) loadAll();
    }, [token]);

    useEffect(() => {
        loadInvoices();
    }, [filterStatus]);

    useEffect(() => {
        getPresentations({ active: "true" }).then(r => setPresentations(r));
    }, []);

    useEffect(() => {
        if (token) {
            getOwners({ is_generic: true }).then(os => {
                if (os?.length) setGenericOwner(os[0]);
            }).catch(() => {});
        }
    }, [token]);

    const loadAll = async () => {
        setLoading(true);
        try {
            const [srvs, prods] = await Promise.all([
                getServices(),
                getProducts({ active: "true" }),
            ]);
            setServices(srvs);
            setProducts(prods);
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
        } catch (err) {
            toast.error("Error al cargar la factura");
        }
    };

    const handleConfirm = async () => {
        try {
            const p = confirmInvoice(selectedInvoice.id).then(updated => {
                setSelectedInvoice(updated);
                loadInvoices();
            });
            await toast.promise(p, {
                loading: 'Confirmando...',
                success: 'Factura confirmada',
                error: (err) => {
                    const errors = err.response?.data?.detail;
                    return Array.isArray(errors) ? errors.join("; ") : apiError(err, "Error al confirmar");
                }
            });
        } catch (err) {}
    };

    const handlePay = async () => {
        try {
            const p = payInvoice(selectedInvoice.id, payMethod).then(updated => {
                setSelectedInvoice(updated);
                setShowPayModal(false);
                loadInvoices();
            });
            await toast.promise(p, {
                loading: 'Registrando pago...',
                success: 'Pago registrado',
                error: (err) => apiError(err, "Error al registrar pago")
            });
        } catch (err) {}
    };

    const handleAddPrescriptionSuggestion = async (suggestion) => {
        try {
            const p = addInvoiceItem(selectedInvoice.id, {
                presentation: suggestion.presentation_id,
                quantity: suggestion.suggested_quantity,
            }).then(() => getInvoice(selectedInvoice.id)).then(updated => {
                setSelectedInvoice(updated);
                loadInvoices();
            });
            await toast.promise(p, {
                loading: 'Agregando producto...',
                success: 'Producto agregado',
                error: (err) => apiError(err, "Error al agregar producto de receta")
            });
        } catch (err) {}
    };

    const handleAddItem = async (e) => {
        e.preventDefault();

        const hasService = Boolean(itemForm.service);
        const hasPresentation = Boolean(itemForm.presentation);

        if (!hasService && !hasPresentation) {
            toast.error("Selecciona un servicio o una presentación");
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
            const p = addInvoiceItem(selectedInvoice.id, payload)
                .then(() => getInvoice(selectedInvoice.id))
                .then(updated => {
                    setSelectedInvoice(updated);
                    setItemForm(EMPTY_ITEM);
                    setItemMode(null);
                    loadInvoices();
                });
            await toast.promise(p, {
                loading: 'Agregando ítem...',
                success: 'Ítem agregado',
                error: (err) => {
                    const detail = err.response?.data;
                    if (Array.isArray(detail)) return detail.join("; ");
                    if (typeof detail === 'object') return Object.values(detail).flat().join("; ");
                    return "Error al agregar ítem";
                }
            });
        } catch (err) {}
    };

    const handleDeleteItem = async (itemId) => {
        const ok = await confirm({ message: "¿Eliminar este ítem de la factura?", confirmText: "Eliminar", dangerMode: true });
        if (!ok) return;
        try {
            const p = deleteInvoiceItem(selectedInvoice.id, itemId)
                .then(() => getInvoice(selectedInvoice.id))
                .then(updated => {
                    setSelectedInvoice(updated);
                    loadInvoices();
                });
            await toast.promise(p, {
                loading: 'Eliminando ítem...',
                success: 'Ítem eliminado',
                error: 'Error al eliminar ítem'
            });
        } catch (err) {}
    };

    const handleTaxRateChange = async (taxRate) => {
        try {
            const p = updateInvoice(selectedInvoice.id, { tax_rate: taxRate })
                .then(() => getInvoice(selectedInvoice.id))
                .then(updated => {
                    setSelectedInvoice(updated);
                    loadInvoices();
                });
            await toast.promise(p, {
                loading: 'Actualizando...',
                success: 'IVA actualizado',
                error: 'Error al actualizar IVA'
            });
        } catch (err) {
            console.log(err);
        }
    };

    const handleServiceSubmit = async (e) => {
        e.preventDefault();
        if (!serviceForm.name.trim()) { toast.error("El nombre es obligatorio"); return; }
        if (!serviceForm.base_price || Number(serviceForm.base_price) < 0) { toast.error("El precio es obligatorio"); return; }
        try {
            const p = editingService ? updateService(editingService.id, serviceForm) : createService(serviceForm);
            await toast.promise(p, {
                loading: editingService ? 'Actualizando...' : 'Creando...',
                success: editingService ? 'Servicio actualizado' : 'Servicio creado',
                error: (err) => apiError(err, "Error al guardar")
            });
            const srvs = await getServices();
            setServices(srvs);
            closeServiceModal();
        } catch (err) {}
    };

    const handleDeleteService = async (id) => {
        const ok = await confirm({ message: "¿Eliminar este servicio del catálogo?", confirmText: "Eliminar", dangerMode: true });
        if (!ok) return;
        try {
            await toast.promise(deleteService(id), { loading: 'Eliminando...', success: 'Servicio eliminado', error: 'Error al eliminar' });
            const srvs = await getServices();
            setServices(srvs);
        } catch (err) {}
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
    };

    const closeDetailModal = () => {
        setShowDetailModal(false);
        setSelectedInvoice(null);
        setItemMode(null);
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
                            setNewInvoiceOwner(null);
                            setNewInvoicePet(null);
                            setNewInvoiceType("direct_sale");
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
                                                <label className="form-label" htmlFor="billing-service">SERVICIO *</label>
                                                <select
                                                    id="billing-service"
                                                    name="billing-service"
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
                                                <label className="form-label" htmlFor="billing-service-quantity">CANTIDAD</label>
                                                <input
                                                    id="billing-service-quantity"
                                                    name="billing-service-quantity"
                                                    type="number" min="0.01" step="0.01" className="input"
                                                    value={itemForm.quantity}
                                                    onChange={e => setItemForm(f => ({ ...f, quantity: e.target.value }))}
                                                />
                                            </div>
                                            <div>
                                                <label className="form-label" htmlFor="billing-service-discount-type">DESCUENTO (opcional)</label>
                                                <select
                                                    id="billing-service-discount-type"
                                                    name="billing-service-discount-type"
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
                                                    <label className="form-label" htmlFor="billing-service-discount-value">
                                                        {itemForm.discount_type === "percentage" ? "PORCENTAJE" : "MONTO A DESCONTAR"}
                                                    </label>
                                                    <input
                                                        id="billing-service-discount-value"
                                                        name="billing-service-discount-value"
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
                                                <label className="form-label" htmlFor="billing-presentation">PRESENTACIÓN *</label>
                                                <select
                                                    id="billing-presentation"
                                                    name="billing-presentation"
                                                    className="select-input"
                                                    value={itemForm.presentation}
                                                    onChange={e => setItemForm(f => ({ ...f, presentation: e.target.value, service: "" }))}
                                                    required
                                                >
                                                    <option value="">— Seleccionar producto —</option>
                                                    {presentations
                                                        .filter(p => !selectedInvoice?.items?.some(i => i.presentation === p.id))
                                                        .map(p => (
                                                        <option key={p.id} value={p.id} disabled={p.stock <= 0}>
                                                            {p.product_name} — {p.name}
                                                            {p.stock <= 0 ? ' (sin stock)' : ` ($${formatCurrency(p.sale_price)} | stock: ${p.stock})`}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="form-label" htmlFor="billing-product-quantity">CANTIDAD</label>
                                                <input
                                                    id="billing-product-quantity"
                                                    name="billing-product-quantity"
                                                    type="number" min="0.01" step="0.01" className="input"
                                                    value={itemForm.quantity}
                                                    onChange={e => setItemForm(f => ({ ...f, quantity: e.target.value }))}
                                                />
                                            </div>
                                            <div>
                                                <label className="form-label" htmlFor="billing-product-discount-type">DESCUENTO (opcional)</label>
                                                <select
                                                    id="billing-product-discount-type"
                                                    name="billing-product-discount-type"
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
                                                    <label className="form-label" htmlFor="billing-product-discount-value">
                                                        {itemForm.discount_type === "percentage" ? "PORCENTAJE" : "MONTO A DESCONTAR"}
                                                    </label>
                                                    <input
                                                        id="billing-product-discount-value"
                                                        name="billing-product-discount-value"
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

                            {/* Productos recetados disponibles */}
                            {selectedInvoice.status === "draft" && (() => {
                                const pendingSuggestions = (selectedInvoice.prescription_suggestions || []).filter(
                                    s => !selectedInvoice.items.some(i => i.presentation === s.presentation_id)
                                );
                                if (pendingSuggestions.length === 0) return null;
                                return (
                                    <div style={{
                                        border: "1px solid #bfdbfe",
                                        borderRadius: "var(--r-lg)",
                                        padding: "12px 14px",
                                        marginBottom: "14px",
                                        background: "#eff6ff",
                                    }}>
                                        <p style={{ fontWeight: "600", fontSize: "12.5px", color: "#1d4ed8", marginBottom: "8px" }}>
                                            Productos recetados — el cliente decide cuáles lleva
                                        </p>
                                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                                            {pendingSuggestions.map(s => (
                                                <div key={s.prescription_item_id} style={{
                                                    display: "flex", alignItems: "center",
                                                    justifyContent: "space-between",
                                                    background: "#fff", borderRadius: "var(--r-md)",
                                                    padding: "7px 10px",
                                                    border: "1px solid #dbeafe",
                                                }}>
                                                    <div>
                                                        <span style={{ fontWeight: "600", fontSize: "13px" }}>
                                                            {s.product_name}
                                                        </span>
                                                        <span style={{ color: "var(--c-text-3)", fontSize: "11.5px", marginLeft: "8px" }}>
                                                            Dosis: {s.dose} · Cant: {s.suggested_quantity} · ${s.unit_price}
                                                        </span>
                                                    </div>
                                                    <button
                                                        className="btn btn-sm"
                                                        style={{ background: "#1d4ed8", color: "#fff", borderColor: "transparent", minWidth: "70px" }}
                                                        onClick={() => handleAddPrescriptionSuggestion(s)}
                                                    >
                                                        Agregar
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })()}

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
                            <div className="modal-footer" style={{ flexDirection: "column", gap: "10px" }}>
                                {/* Indicador de pasos — solo para facturas en tránsito */}
                                {(selectedInvoice.status === "draft" || selectedInvoice.status === "confirmed") && (
                                    <div style={{ display: "flex", alignItems: "center", width: "100%", gap: "8px", paddingBottom: "4px" }}>
                                        {[
                                            { label: "Confirmar", step: 1, done: selectedInvoice.status === "confirmed" },
                                            { label: "Registrar Pago", step: 2, done: false },
                                        ].map((s, i, arr) => (
                                            <div key={s.step} style={{ display: "flex", alignItems: "center", flex: i < arr.length - 1 ? "none" : 1, gap: "6px" }}>
                                                <span style={{
                                                    width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                                                    display: "flex", alignItems: "center", justifyContent: "center",
                                                    fontSize: 11, fontWeight: 700,
                                                    background: s.done ? "#059669" : (selectedInvoice.status === "confirmed" && s.step === 2 ? "#1d4ed8" : "var(--c-border)"),
                                                    color: "#fff",
                                                }}>
                                                    {s.done ? "✓" : s.step}
                                                </span>
                                                <span style={{
                                                    fontSize: 12, fontWeight: 600,
                                                    color: s.done ? "#059669" : (selectedInvoice.status === "confirmed" && s.step === 2 ? "#1d4ed8" : "var(--c-text-3)"),
                                                    whiteSpace: "nowrap",
                                                }}>
                                                    {s.label}
                                                </span>
                                                {i < arr.length - 1 && (
                                                    <div style={{ flex: 1, height: 2, minWidth: 20, background: s.done ? "#059669" : "var(--c-border)", marginLeft: 4 }} />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                                <div style={{ display: "flex", gap: "8px", width: "100%" }}>
                                    {selectedInvoice.status === "draft" && (
                                        <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleConfirm}>
                                            Confirmar cobro
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
                            <fieldset className="form-group" style={{ border: "none", margin: 0, padding: 0 }}>
                                <legend className="form-label">MÉTODO DE PAGO</legend>
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
                            </fieldset>
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

                            {genericOwner && (
                            <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                style={{ marginBottom: "16px" }}
                                onClick={() => {
                                    setNewInvoiceOwner({ id: genericOwner.id, label: genericOwner.name });
                                    setNewInvoicePet(null);
                                    setNewInvoiceType("direct_sale");
                                }}
                            >
                                Venta a público general
                            </button>
                        )}

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "20px" }}>
                                <div>
                                    <label className="label" htmlFor="new-invoice-owner">Propietario</label>
                                    <SearchSelect
                                        id="new-invoice-owner"
                                        name="new-invoice-owner"
                                        value={newInvoiceOwner}
                                        onChange={item => { setNewInvoiceOwner(item); setNewInvoicePet(null); }}
                                        onSearch={q => getOwners({ search: q }).then(os => os.filter(o => !o.is_generic).map(o => ({ id: o.id, label: o.name })))}
                                        placeholder="Buscar propietario..."
                                    />
                                </div>

                                <div>
                                    <label className="label" htmlFor="new-invoice-pet">Mascota {newInvoiceOwner?.id === genericOwner?.id ? "(no requerida)" : "*"}</label>
                                    <SearchSelect
                                        id="new-invoice-pet"
                                        name="new-invoice-pet"
                                        value={newInvoicePet}
                                        onChange={item => setNewInvoicePet(item)}
                                        onSearch={q => getPets({ search: q, owner: newInvoiceOwner?.id }).then(ps => ps.map(p => ({ id: p.id, label: p.name })))}
                                        placeholder={newInvoiceOwner ? "Buscar mascota..." : "Selecciona propietario primero"}
                                        disabled={!newInvoiceOwner || newInvoiceOwner?.id === genericOwner?.id}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="label" htmlFor="new-invoice-type">Tipo de Factura</label>
                                <select
                                    id="new-invoice-type"
                                    name="new-invoice-type"
                                    className="input"
                                    value={newInvoiceType}
                                    onChange={e => setNewInvoiceType(e.target.value)}
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
                                        if (!newInvoiceOwner) { toast.error("Selecciona un propietario"); return; }
                                        const isGeneric = newInvoiceOwner?.id === genericOwner?.id;
                                        if (!isGeneric && !newInvoicePet) { toast.error("Selecciona una mascota"); return; }
                                        const p = createInvoice({
                                            owner: newInvoiceOwner.id,
                                            pet: isGeneric ? undefined : newInvoicePet.id,
                                            invoice_type: newInvoiceType,
                                        }).then(async (newInv) => {
                                            setShowNewInvoiceModal(false);
                                            await loadInvoices();
                                            await openInvoiceDetail(newInv);
                                        });

                                        await toast.promise(p, {
                                            loading: 'Creando factura...',
                                            success: 'Factura creada',
                                            error: (err) => err.response?.data?.detail || "Error al crear factura"
                                        });
                                    } catch (err) {
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
