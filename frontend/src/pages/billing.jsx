import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useConfirm } from "../components/ConfirmDialog";
import { apiError } from "../utils/apiError";
import {
    getInvoices, getInvoice, createInvoice, confirmInvoice, payInvoice, directPayInvoice,
    addInvoiceItem, getServices, downloadInvoicePDF,
} from "../api/billing";
import { extractFilename, triggerDownload } from "../utils/downloadBlob";
import { getPresentations } from "../api/inventory";
import { getOwners } from "../api/pets";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import { toast } from "sonner";
import SearchSelect from "../components/SearchSelect";
import DateRangePicker from "../components/DateRangePicker";
import s from "./billing.module.css";

const FILTER_KEYS = ["status", "invoice_type", "created_from", "created_to", "paid_from", "paid_to"];
const STATUS_LABELS = { draft: "Borrador", confirmed: "Confirmada", paid: "Pagada", cancelled: "Cancelada" };
const TYPE_LABELS = { consultation: "Consulta", direct_sale: "Venta directa" };
const PAYMENT_METHODS = [
    { value: "cash", label: "Efectivo" },
    { value: "card", label: "Tarjeta" },
    { value: "transfer", label: "Transferencia" },
    { value: "other", label: "Otro" },
];

const DOT_COLOR = {
    draft: "var(--c-text-4)",
    confirmed: "var(--c-info-text)",
    paid: "var(--c-success-text)",
    cancelled: "var(--c-danger-text)",
};

const Billing = () => {
    const { token, initializing, can } = useAuth();
    const confirm = useConfirm();
    const [searchParams, setSearchParams] = useSearchParams();
    const [loading, setLoading] = useState(true);
    const requestIdRef = useRef(0);

    const [invoices, setInvoices] = useState([]);
    const [genericOwner, setGenericOwner] = useState(null);

    const [filters, setFilters] = useState(() => {
        const initial = {};
        for (const key of FILTER_KEYS) initial[key] = searchParams.get(key) || "";
        return initial;
    });

    const [selectedInvoice, setSelectedInvoice] = useState(null);
    const [showDetailModal, setShowDetailModal] = useState(false);
    const [showPayModal, setShowPayModal] = useState(false);
    const [payMethod, setPayMethod] = useState("cash");
    const [downloadingInvoiceId, setDownloadingInvoiceId] = useState(null);

    const [showNewInvoiceModal, setShowNewInvoiceModal] = useState(false);

    const loadInvoices = async (currentFilters) => {
        const requestId = ++requestIdRef.current;
        try {
            const params = {};
            for (const key of FILTER_KEYS) if (currentFilters[key]) params[key] = currentFilters[key];
            const data = await getInvoices(params);
            if (requestId === requestIdRef.current) setInvoices(data);
        } catch {
            // Silencioso — el usuario ve lista vacía
        }
    };

    const loadAll = async () => {
        setLoading(requestIdRef.current === 0);
        try {
            const owners = await getOwners({ is_generic: "true" });
            setGenericOwner((Array.isArray(owners) ? owners : owners?.results || [])[0] || null);
            await loadInvoices(filters);
        } catch {
            // Silencioso — loadInvoices maneja su error
        } finally { setLoading(false); }
    };

    useEffect(() => { if (token) { loadAll(); } }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        const timer = setTimeout(() => loadInvoices(filters), 300);
        return () => clearTimeout(timer);
    }, [filters.status, filters.invoice_type, filters.created_from, filters.created_to, filters.paid_from, filters.paid_to]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'F11' && can("invoice.create") && !showNewInvoiceModal && !showDetailModal) {
                e.preventDefault();
                setShowNewInvoiceModal(true);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [can, showNewInvoiceModal, showDetailModal]);

    const updateFilter = (key, value) => {
        const next = { ...filters, [key]: value };
        setFilters(next);
        const params = new URLSearchParams();
        for (const k of FILTER_KEYS) if (next[k]) params.set(k, next[k]);
        setSearchParams(params, { replace: true });
    };

    const clearFilters = () => {
        const empty = {};
        for (const key of FILTER_KEYS) empty[key] = "";
        setFilters(empty);
        setSearchParams({}, { replace: true });
    };

    const openInvoiceDetail = async (invoice) => {
        try {
            const detail = await getInvoice(invoice.public_id);
            setSelectedInvoice(detail);
            setShowDetailModal(true);
        } catch { toast.error("Error al cargar la factura"); }
    };

    const closeDetailModal = () => {
        setShowDetailModal(false);
        setSelectedInvoice(null);
        setShowPayModal(false);
    };

    const handleDownloadInvoicePDF = async (publicId) => {
        setDownloadingInvoiceId(publicId);
        try {
            const { blob, contentDisposition } = await downloadInvoicePDF(publicId);
            const filename = extractFilename(contentDisposition, "factura.pdf");
            triggerDownload(blob, filename);
        } catch (err) { toast.error(apiError(err, "Error al descargar PDF")); }
        finally { setDownloadingInvoiceId(null); }
    };

    const handleConfirm = async () => {
        try {
            const updated = await toast.promise(confirmInvoice(selectedInvoice.public_id), {
                loading: 'Confirmando...', success: 'Confirmada', error: (err) => apiError(err, "Error")
            });
            setSelectedInvoice(updated);
            loadInvoices(filters);
        } catch {
            // toast.promise ya muestra el error
        }
    };

    const handlePay = async () => {
        try {
            const updated = await toast.promise(payInvoice(selectedInvoice.public_id, payMethod), {
                loading: 'Registrando...', success: 'Pagada', error: (err) => apiError(err, "Error")
            });
            setSelectedInvoice(updated);
            setShowPayModal(false);
            loadInvoices(filters);
        } catch {
            // toast.promise ya muestra el error
        }
    };

    const handleDirectPay = async () => {
        try {
            const updated = await toast.promise(directPayInvoice(selectedInvoice.public_id, payMethod), {
                loading: 'Cobrando...', success: 'Cobrada', error: (err) => apiError(err, "Error")
            });
            setSelectedInvoice(updated);
            setShowPayModal(false);
            loadInvoices(filters);
        } catch {
            // toast.promise ya muestra el error
        }
    };

    const formatDate = (dateString) => dateString ? new Date(dateString).toLocaleDateString("es-ES", { year: "numeric", month: "short", day: "numeric" }) : "—";
    const formatCurrency = (amount) => Number(amount || 0).toFixed(2);

    if (initializing || loading) return <div style={{ display: "flex", justifyContent: "center", padding: "100px", color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</div>;

    const isDirectSaleDraft = selectedInvoice?.invoice_type === "direct_sale" && selectedInvoice?.status === "draft";

    return (
        <div className={s.billingContainer}>
            <div className={s.pageHeader}>
                <h1 className={s.mainTitle}>Cobros</h1>
            </div>

            <div className={s.filterBar}>
                <div className={s.filterItem}>
                    <Icon.Filter s={12} c="var(--c-text-4)" />
                    <select value={filters.status} onChange={e => updateFilter("status", e.target.value)}>
                        <option value="">Estado</option>
                        {Object.entries(STATUS_LABELS).map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
                    </select>
                </div>
                <div className={s.filterItem}>
                    <Icon.Receipt s={12} c="var(--c-text-4)" />
                    <select value={filters.invoice_type} onChange={e => updateFilter("invoice_type", e.target.value)}>
                        <option value="">Tipo</option>
                        {Object.entries(TYPE_LABELS).map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
                    </select>
                </div>
                <DateRangePicker from={filters.created_from} to={filters.created_to} onChange={(f, t) => { updateFilter("created_from", f); updateFilter("created_to", t); }} placeholder="Creado" />
                <button className="btn btn-ghost btn-xs" onClick={clearFilters} style={{ color: "var(--c-text-4)" }}>Limpiar</button>
                {can("invoice.create") && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "6px" }}
                        onClick={() => setShowNewInvoiceModal(true)}
                        title="Atajo: F11"
                    >
                        + Cobro
                        <kbd style={{
                            fontSize: "10px", fontWeight: 600, padding: "1px 5px",
                            borderRadius: "3px", border: "1px solid rgba(255,255,255,0.3)",
                            background: "rgba(255,255,255,0.15)", color: "inherit",
                            lineHeight: "16px",
                        }}>F11</kbd>
                    </button>
                )}
            </div>

            {invoices.length === 0 ? <div className="empty-state"><p className="empty-state-title">No hay cobros</p></div> : (
                <table className={s.tableCompact}>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Paciente / Cliente</th>
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
                                <td style={{ color: "var(--c-text-3)" }}>#{inv.id}</td>
                                <td>
                                    <div style={{ color: "var(--c-text)" }}>{inv.pet_name}</div>
                                    <div style={{ fontSize: "11px", color: "var(--c-text-3)" }}>{inv.owner_name}</div>
                                </td>
                                <td style={{ fontSize: "12px" }}>{inv.invoice_type === "direct_sale" ? "Venta directa" : "Consulta"}</td>
                                <td>
                                    <div className={s.statusContainer}>
                                        <span className={s.statusDot} style={{ background: DOT_COLOR[inv.status] }} />
                                        {STATUS_LABELS[inv.status]}
                                    </div>
                                </td>
                                <td style={{ color: "var(--c-text-3)" }}>{formatDate(inv.created_at)}</td>
                                <td style={{ textAlign: "right", color: "var(--c-text)" }}>${formatCurrency(inv.total)}</td>
                                <td style={{ textAlign: "right" }}>
                                    <button className={s.actionBtn} onClick={() => openInvoiceDetail(inv)}><Icon.Eye s={14} /></button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}

            {/* Detail Modal */}
            {showDetailModal && selectedInvoice && (
                <div className="modal-overlay">
                    <div className="modal modal-lg">
                        <div className="modal-header">
                            <div>
                                <h3 className={s.mainTitle} style={{ fontSize: "16px" }}>#{selectedInvoice.id}</h3>
                                <div className={s.statusContainer} style={{ marginTop: "4px" }}>
                                    <span className={s.statusDot} style={{ background: DOT_COLOR[selectedInvoice.status] }} />
                                    {STATUS_LABELS[selectedInvoice.status]}
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: "8px" }}>
                                <button className="btn btn-secondary btn-sm" onClick={() => handleDownloadInvoicePDF(selectedInvoice.public_id)} disabled={downloadingInvoiceId === selectedInvoice.public_id}>
                                    {downloadingInvoiceId === selectedInvoice.public_id ? <Icon.Loader s={12} /> : <Icon.Download s={12} />} PDF
                                </button>
                                <button className="modal-close" onClick={closeDetailModal}><Icon.X s={14} /></button>
                            </div>
                        </div>
                        <div className="modal-body">
                            <div className={s.infoGrid}>
                                <div><p className={s.infoLabel}>Paciente</p><p className={s.infoValue}>{selectedInvoice.pet_name}</p></div>
                                <div><p className={s.infoLabel}>Propietario</p><p className={s.infoValue}>{selectedInvoice.owner_name}</p></div>
                                <div><p className={s.infoLabel}>Fecha</p><p className={s.infoValue}>{formatDate(selectedInvoice.created_at)}</p></div>
                            </div>

                            <p style={{ fontSize: "11px", fontWeight: "500", color: "var(--c-text-3)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.05em" }}>Conceptos</p>
                            <table className={s.tableCompact} style={{ border: "1px solid var(--c-border)" }}>
                                <thead>
                                    <tr>
                                        <th>Descripción</th>
                                        <th>Cant.</th>
                                        <th style={{ textAlign: "right" }}>Total</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selectedInvoice.items.map(item => (
                                        <tr key={item.id}>
                                            <td>{item.description}</td>
                                            <td>{item.quantity}</td>
                                            <td style={{ textAlign: "right" }}>${formatCurrency(item.subtotal)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            <div className={s.totalsSection}>
                                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                                    <div style={{ minWidth: "200px" }}>
                                        <div className={s.totalRow}><span>Subtotal</span><span>${formatCurrency(selectedInvoice.subtotal)}</span></div>
                                        <div className={s.totalRow}><span>IVA</span><span>${formatCurrency(selectedInvoice.tax_amount)}</span></div>
                                        <div className={s.grandTotal}><span>Total</span><span>${formatCurrency(selectedInvoice.total)}</span></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="modal-footer">
                            <div style={{ display: "flex", gap: "8px", width: "100%" }}>
                                {isDirectSaleDraft && (
                                    <button className="btn btn-primary btn-md" style={{ flex: 1, background: "var(--c-success-text)", borderColor: "var(--c-success-text)", color: "#fff" }} onClick={() => { setPayMethod("cash"); setShowPayModal(true); }}>
                                        Cobrar
                                    </button>
                                )}
                                {selectedInvoice.status === "draft" && !isDirectSaleDraft && (
                                    <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleConfirm}>Confirmar</button>
                                )}
                                {selectedInvoice.status === "confirmed" && (
                                    <button className="btn btn-primary btn-md" style={{ flex: 1, background: "var(--c-success-text)", borderColor: "var(--c-success-text)", color: "#fff" }} onClick={() => setShowPayModal(true)}>Registrar Pago</button>
                                )}
                                <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeDetailModal}>Cerrar</button>
                            </div>
                        </div>
                    </div>

                    {/* Pay Method Modal */}
                    {showPayModal && (
                        <div className="modal-overlay" style={{ zIndex: 1001 }}>
                            <div className="modal" style={{ maxWidth: "360px" }}>
                                <div className="modal-header">
                                    <h3 style={{ fontSize: "15px", fontWeight: 600, color: "var(--c-text)" }}>
                                        {isDirectSaleDraft ? "Cobrar venta directa" : "Método de pago"}
                                    </h3>
                                    <button className="modal-close" onClick={() => setShowPayModal(false)}><Icon.X s={14} /></button>
                                </div>
                                <div className="modal-body">
                                    <div style={{ marginBottom: "16px" }}>
                                        <label style={{ fontSize: "12px", fontWeight: 500, color: "var(--c-text-3)", display: "block", marginBottom: "8px" }}>
                                            Método
                                        </label>
                                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                                            {PAYMENT_METHODS.map(m => (
                                                <button
                                                    key={m.value}
                                                    className={`btn ${payMethod === m.value ? "btn-primary" : "btn-secondary"} btn-sm`}
                                                    onClick={() => setPayMethod(m.value)}
                                                >
                                                    {m.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <p style={{ fontSize: "12px", color: "var(--c-text-3)" }}>
                                        Total: <strong style={{ color: "var(--c-text)" }}>${formatCurrency(selectedInvoice.total)}</strong>
                                    </p>
                                </div>
                                <div className="modal-footer">
                                    <button className="btn btn-secondary btn-sm" onClick={() => setShowPayModal(false)}>Cancelar</button>
                                    <button
                                        className="btn btn-primary btn-sm"
                                        style={{ background: "var(--c-success-text)", borderColor: "var(--c-success-text)", color: "#fff" }}
                                        onClick={isDirectSaleDraft ? handleDirectPay : handlePay}
                                    >
                                        {isDirectSaleDraft ? "Cobrar" : "Registrar Pago"}
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* New Invoice Modal (Venta Directa) */}
            {showNewInvoiceModal && (
                <NewInvoiceModal
                    genericOwner={genericOwner}
                    onClose={() => setShowNewInvoiceModal(false)}
                    onPaid={() => { setShowNewInvoiceModal(false); loadInvoices(filters); }}
                    confirm={confirm}
                />
            )}
        </div>
    );
};

/* ── NewInvoiceModal Component ── */
const NewInvoiceModal = ({ genericOwner, onClose, onPaid, confirm }) => {
    const [items, setItems] = useState([]);
    const [presentationLine, setPresentationLine] = useState({ presentation: null, quantity: "1" });
    const [serviceLine, setServiceLine] = useState({ service: null, quantity: "1" });
    const [paymentMethod, setPaymentMethod] = useState("cash");
    const [processing, setProcessing] = useState(false);
    const [presentationCache, setPresentationCache] = useState([]);
    const [serviceCache, setServiceCache] = useState([]);

    useEffect(() => {
        getPresentations({ active: "true" }).then(data => {
            setPresentationCache(Array.isArray(data) ? data : data?.results || []);
        }).catch(() => {});
        getServices({ active: "true" }).then(data => {
            setServiceCache(Array.isArray(data) ? data : data?.results || []);
        }).catch(() => {});
    }, []);

    const handleClose = async () => {
        if (items.length > 0) {
            const ok = await confirm(
                "¿Descartar este cobro?",
                "Los ítems no se guardarán.",
                "Descartar",
                "Continuar editando"
            );
            if (!ok) return;
        }
        onClose();
    };

    const handleProductSearch = async (q) => {
        const lower = q.trim().toLowerCase();
        const source = lower
            ? await getPresentations({ search: q }).then(d => Array.isArray(d) ? d : d?.results || []).catch(() => [])
            : presentationCache;
        const filtered = lower
            ? source.filter(p => p.product_name?.toLowerCase().includes(lower) || p.name?.toLowerCase().includes(lower))
            : source;
        return filtered.slice(0, 8).map(p => ({
            id: p.id,
            label: `${p.product_name} — ${p.name} ($${Number(p.sale_price).toFixed(2)})`,
        }));
    };

    const handleServiceSearch = async (q) => {
        const lower = q.trim().toLowerCase();
        const source = lower
            ? await getServices({ active: "true", search: q }).then(d => Array.isArray(d) ? d : d?.results || []).catch(() => [])
            : serviceCache;
        const filtered = lower
            ? source.filter(s => s.name?.toLowerCase().includes(lower))
            : source;
        return filtered.slice(0, 8).map(s => ({
            id: s.id,
            label: `${s.name} — $${Number(s.base_price).toFixed(2)}`,
        }));
    };

    const addPresentationItem = () => {
        if (!presentationLine.presentation) return;
        const pres = presentationCache.find(p => p.id === presentationLine.presentation.id);
        if (!pres) return;
        const qty = Math.max(1, parseInt(presentationLine.quantity) || 1);
        if (pres.stock < qty) {
            toast.error(`Stock insuficiente (${pres.stock} disponible).`);
            return;
        }
        const existing = items.find(i => i.type === "product" && i.id === pres.id);
        if (existing) {
            const newQty = existing.quantity + qty;
            if (pres.stock < newQty) {
                toast.error(`Stock insuficiente (${pres.stock} disponible, ya tienes ${existing.quantity}).`);
                return;
            }
            setItems(prev => prev.map(i => i.id === pres.id && i.type === "product"
                ? { ...i, quantity: newQty }
                : i
            ));
        } else {
            setItems(prev => [...prev, {
                type: "product",
                id: pres.id,
                name: `${pres.product_name} — ${pres.name}`,
                quantity: qty,
                unit_price: pres.sale_price,
            }]);
        }
        setPresentationLine({ presentation: null, quantity: "1" });
    };

    const addServiceItem = () => {
        if (!serviceLine.service) return;
        const svc = serviceCache.find(s => s.id === serviceLine.service.id);
        if (!svc) return;
        const qty = Math.max(1, parseInt(serviceLine.quantity) || 1);
        const existing = items.find(i => i.type === "service" && i.id === svc.id);
        if (existing) {
            setItems(prev => prev.map(i => i.id === svc.id && i.type === "service"
                ? { ...i, quantity: existing.quantity + qty }
                : i
            ));
        } else {
            setItems(prev => [...prev, {
                type: "service",
                id: svc.id,
                name: svc.name,
                quantity: qty,
                unit_price: svc.base_price,
            }]);
        }
        setServiceLine({ service: null, quantity: "1" });
    };

    const removeItem = (idx) => {
        setItems(prev => prev.filter((_, i) => i !== idx));
    };

    const subtotal = items.reduce((sum, i) => sum + i.quantity * Number(i.unit_price), 0);

    const handleCobrar = async () => {
        if (items.length === 0) {
            toast.error("Agrega al menos un ítem.");
            return;
        }
        if (!genericOwner) {
            toast.error("No se encontró el propietario genérico. Verifica la configuración.");
            return;
        }
        setProcessing(true);
        try {
            const invoice = await createInvoice({ owner: genericOwner.id });
            for (const item of items) {
                const payload = item.type === "product"
                    ? { presentation: item.id, quantity: String(item.quantity) }
                    : { service: item.id, quantity: String(item.quantity) };
                await addInvoiceItem(invoice.public_id, payload);
            }
            await directPayInvoice(invoice.public_id, paymentMethod);
            toast.success("Venta directa cobrada");
            onPaid();
        } catch (err) {
            toast.error(apiError(err, "Error al procesar el cobro. Intenta de nuevo."));
        } finally {
            setProcessing(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={handleClose}>
            <div className="modal modal-lg" onClick={e => e.stopPropagation()} style={{ maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
                <div className="modal-header" style={{ flexShrink: 0 }}>
                    <div>
                        <h3 style={{ fontSize: "16px", fontWeight: 600, color: "var(--c-text)" }}>Nuevo Cobro</h3>
                        <span style={{ fontSize: "12px", color: "var(--c-text-3)" }}>Venta directa</span>
                    </div>
                    <button className="modal-close" onClick={handleClose}><Icon.X s={14} /></button>
                </div>

                {/* Step 1: Add items */}
                <div className="modal-body" style={{ flex: 1, overflow: "auto" }}>
                    <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
                        {/* Product */}
                        <div style={{ flex: "1 1 300px" }}>
                            <label style={{ fontSize: "11px", fontWeight: 600, color: "var(--c-text-3)", display: "block", marginBottom: "4px", textTransform: "uppercase" }}>Producto</label>
                            <div style={{ display: "flex", gap: "8px" }}>
                                <div style={{ flex: 1 }}>
                                    <SearchSelect
                                        placeholder="Buscar producto..."
                                        value={presentationLine.presentation}
                                        onChange={item => setPresentationLine(prev => ({ ...prev, presentation: item }))}
                                        onSearch={handleProductSearch}
                                    />
                                </div>
                                <input
                                    type="number"
                                    className="input"
                                    style={{ width: "70px", height: "38px", textAlign: "center" }}
                                    value={presentationLine.quantity}
                                    onChange={e => setPresentationLine(prev => ({ ...prev, quantity: e.target.value }))}
                                    min="1"
                                />
                                <button className="btn btn-primary btn-sm" onClick={addPresentationItem} disabled={!presentationLine.presentation}>
                                    <Icon.Plus s={14} />
                                </button>
                            </div>
                        </div>

                        {/* Service */}
                        <div style={{ flex: "1 1 300px" }}>
                            <label style={{ fontSize: "11px", fontWeight: 600, color: "var(--c-text-3)", display: "block", marginBottom: "4px", textTransform: "uppercase" }}>Servicio</label>
                            <div style={{ display: "flex", gap: "8px" }}>
                                <div style={{ flex: 1 }}>
                                    <SearchSelect
                                        placeholder="Buscar servicio..."
                                        value={serviceLine.service}
                                        onChange={item => setServiceLine(prev => ({ ...prev, service: item }))}
                                        onSearch={handleServiceSearch}
                                    />
                                </div>
                                <input
                                    type="number"
                                    className="input"
                                    style={{ width: "70px", height: "38px", textAlign: "center" }}
                                    value={serviceLine.quantity}
                                    onChange={e => setServiceLine(prev => ({ ...prev, quantity: e.target.value }))}
                                    min="1"
                                />
                                <button className="btn btn-primary btn-sm" onClick={addServiceItem} disabled={!serviceLine.service}>
                                    <Icon.Plus s={14} />
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Items Table */}
                    <table className={s.tableCompact} style={{ border: "1px solid var(--c-border)" }}>
                        <thead>
                            <tr>
                                <th>Tipo</th>
                                <th>Concepto</th>
                                <th>Cant.</th>
                                <th style={{ textAlign: "right" }}>P. Unit</th>
                                <th style={{ textAlign: "right" }}>Subtotal</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan="6" style={{ textAlign: "center", padding: "24px", color: "var(--c-text-3)" }}>
                                        Agrega productos o servicios para comenzar.
                                    </td>
                                </tr>
                            ) : items.map((item, idx) => (
                                <tr key={`${item.type}-${item.id}-${idx}`}>
                                    <td style={{ fontSize: "11px", color: "var(--c-text-3)" }}>
                                        {item.type === "product" ? <Icon.Package s={12} /> : <Icon.Stethoscope s={12} />}
                                    </td>
                                    <td style={{ fontWeight: 500 }}>{item.name}</td>
                                    <td style={{ textAlign: "center" }}>{item.quantity}</td>
                                    <td style={{ textAlign: "right" }}>${Number(item.unit_price).toFixed(2)}</td>
                                    <td style={{ textAlign: "right", fontWeight: 500 }}>
                                        ${(item.quantity * Number(item.unit_price)).toFixed(2)}
                                    </td>
                                    <td style={{ textAlign: "right" }}>
                                        <button className={s.actionBtn} onClick={() => removeItem(idx)} disabled={processing}>
                                            <Icon.Trash s={13} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {/* Total */}
                    {items.length > 0 && (
                        <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
                            <div style={{ minWidth: "180px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "13px", color: "var(--c-text-2)" }}>
                                    <span>Subtotal</span>
                                    <span>${subtotal.toFixed(2)}</span>
                                </div>
                                {/* Note: IVA se calcula en backend con tax_rate de la org */}
                                <div style={{ display: "flex", justifyContent: "space-between", padding: "12px 0 4px", borderTop: "1px solid var(--c-subtle)", fontSize: "16px", fontWeight: 600, color: "var(--c-text)" }}>
                                    <span>Total estimado</span>
                                    <span>${subtotal.toFixed(2)}</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer: Payment method + Cobrar */}
                <div className="modal-footer" style={{ flexShrink: 0, borderTop: "1px solid var(--c-border)", paddingTop: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px", width: "100%" }}>
                        <div style={{ flex: 1 }}>
                            <label style={{ fontSize: "11px", fontWeight: 500, color: "var(--c-text-3)", display: "block", marginBottom: "4px" }}>
                                Método de pago
                            </label>
                            <div style={{ display: "flex", gap: "6px" }}>
                                {PAYMENT_METHODS.map(m => (
                                    <button
                                        key={m.value}
                                        className={`btn ${paymentMethod === m.value ? "btn-primary" : "btn-secondary"} btn-xs`}
                                        onClick={() => setPaymentMethod(m.value)}
                                        disabled={processing}
                                    >
                                        {m.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <button className="btn btn-secondary btn-sm" onClick={handleClose} disabled={processing}>
                            Cancelar
                        </button>
                        <button
                            className="btn btn-primary btn-sm"
                            style={{ background: "var(--c-success-text)", borderColor: "var(--c-success-text)", color: "#fff", minWidth: "100px" }}
                            onClick={handleCobrar}
                            disabled={items.length === 0 || processing || !genericOwner}
                        >
                            {processing ? <Icon.Loader s={14} /> : "Cobrar"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Billing;
