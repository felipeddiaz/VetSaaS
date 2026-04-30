import { useEffect, useState, useMemo } from "react";
import { useConfirm } from "../components/ConfirmDialog";
import { apiError } from "../utils/apiError";
import {
    getProducts, createProduct, updateProduct, deleteProduct,
    adjustStock, getUnitChoices,
} from "../api/inventory";
import { useAuth } from "../auth/authContext";
import { Icon } from "../components/icons";
import { toast } from "sonner";
import s from "./inventory.module.css";

// ── Constants ─────────────────────────────────────────────
const CATEGORY_LABELS = {
    medication: "Medicamento", food: "Alimento",
    accessory: "Accesorio", other: "Otro",
};

const CATEGORY_UNITS = {
    medication: ["tablet", "capsule", "ml", "vial", "ampoule", "bottle", "tube", "unit"],
    food:       ["kg", "g", "bag", "unit"],
    accessory:  ["piece", "unit"],
    other:      null, // todas las unidades
};

const EMPTY_PRODUCT = {
    name: "", internal_code: "", description: "",
    category: "other", requires_prescription: false,
    base_unit: "unit", sale_price: "", stock: "", min_stock: "",
};
const EMPTY_ADJUST = { movement_type: "in", quantity: 1, reason: "" };

// ── Transformación de form plano → payload API anidado ────
const buildProductPayload = (formData) => ({
    name: formData.name,
    ...(formData.internal_code && { internal_code: formData.internal_code }),
    description: formData.description,
    category: formData.category,
    requires_prescription: formData.requires_prescription,
    presentation: {
        base_unit: formData.base_unit,
        quantity: 1,  // factor base — no se usa en Fase 1, cambia en Fase 3
        sale_price: formData.sale_price,
        stock: formData.stock,
        min_stock: formData.min_stock,
    },
});

// ── Helpers ───────────────────────────────────────────────
// R1: siempre acceder via pres = product.presentation || {}
// R2: parseFloat con fallback para strings del API ("100.00")
const stockStatus = (product) => {
    const pres = product.presentation || {};
    const stock = parseFloat(pres.stock ?? 0) || 0;
    const min = parseFloat(pres.min_stock ?? 0) || 0;
    if (stock <= 0) return { pct: 0, state: "crit", label: "Agotado" };
    if (min > 0 && stock < min) return { pct: Math.min((stock / min) * 100, 100), state: "low", label: "Stock bajo" };
    const top = min > 0 ? min * 3 : 100;
    return { pct: Math.max(Math.min((stock / top) * 100, 100), 15), state: "ok", label: "Normal" };
};

const fmt = (n) => Math.round(parseFloat(n ?? 0) || 0);
const fmtCur = (n, locale = navigator.language) =>
    (parseFloat(n ?? 0) || 0).toLocaleString(locale, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    });

// ── Category icon ─────────────────────────────────────────
const ICON_COLOR = { medication: "#3b82f6", food: "#0d9488", accessory: "#7c3aed", other: "#94a3b8" };
const CATEGORY_ICON = { medication: Icon.Pill, food: Icon.ShoppingBag, accessory: Icon.Package, other: Icon.Box };

const CategoryIcon = ({ category, size = 18 }) => {
    const c = ICON_COLOR[category] || ICON_COLOR.other;
    const IconComp = CATEGORY_ICON[category] || CATEGORY_ICON.other;
    return <IconComp s={size} c={c} />;
};

const ICO_CLS = { medication: s.icoMed, food: s.icoFood, accessory: s.icoAcc, other: s.icoOther };
const BADGE_CLS = { medication: s.badgeBlue, food: s.badgeGreen, accessory: s.badgePurple, other: s.badgeGray };

// ── SortableHeader ────────────────────────────────────────
    const SortHeader = ({ col, label, sortCol, sortDir, onSort, align = "left" }) => {
    const active = sortCol === col;
    const ArrowIcon = active ? (sortDir === "asc" ? Icon.ArrowUp : Icon.ArrowDown) : Icon.ArrowUpDown;
    return (
        <th
            className={`${s.th} ${s.sortable}`}
            style={{ textAlign: align }}
            onClick={() => onSort(col)}
        >
            <span className={s.thInner}>
                {label}
                <span className={`${s.sortArrow} ${active ? s.active : ""}`}>
                    <ArrowIcon s={11} c="currentColor" />
                </span>
            </span>
        </th>
    );
};

// ── Component ─────────────────────────────────────────────
const Inventory = () => {
    const { token, user, initializing } = useAuth();
    const confirm = useConfirm();

    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);

    const [unitChoices, setUnitChoices] = useState([]);
    const [unitsLoaded, setUnitsLoaded] = useState(false);

    const [filterCategory, setFilterCategory] = useState("");
    const [searchText, setSearchText] = useState("");
    const [stockFilter, setStockFilter] = useState("");
    const [sortCol, setSortCol] = useState("name");
    const [sortDir, setSortDir] = useState("asc");
    const [viewMode, setViewMode] = useState("table");
    const [alertDismissed, setAlertDismissed] = useState(false);

    const [showProductModal, setShowProductModal] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_PRODUCT);
    const [formErrors, setFormErrors] = useState({});

    const [showAdjustModal, setShowAdjustModal] = useState(false);
    const [adjustingProduct, setAdjustingProduct] = useState(null);
    const [adjustForm, setAdjustForm] = useState(EMPTY_ADJUST);

    const [saving, setSaving] = useState(false);

    useEffect(() => { if (token) loadAll(); }, [token]);

    // Cargar catálogo de unidades una sola vez (R9)
    useEffect(() => {
        getUnitChoices()
            .then(data => { setUnitChoices(data); setUnitsLoaded(true); })
            .catch(() => setUnitsLoaded(true));
    }, []);

    const loadAll = async () => {
        setLoading(true);
        try {
            const prods = await getProducts();
            setProducts(prods);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const canManage = user?.role !== "ASSISTANT";

    // ── Metrics (R1 + R2 + R11) ───────────────────────────
    const metrics = useMemo(() => {
        const active = products.filter(p => p.is_active !== false);
        return {
            total: active.length,
            medications: active.filter(p => p.category === "medication").length,
            // R11: confiar en is_low_stock del backend, no duplicar lógica
            lowStock: active.filter(p => p.presentation?.is_low_stock).length,
            outOfStock: active.filter(p => parseFloat((p.presentation || {}).stock ?? 0) <= 0).length,
            totalVal: active.reduce((acc, p) => {
                const pres = p.presentation || {};
                return acc + (parseFloat(pres.sale_price ?? 0) || 0) * (parseFloat(pres.stock ?? 0) || 0);
            }, 0),
        };
    }, [products]);

    const alertProducts = useMemo(() => {
        const low = products.filter(p => p.is_active !== false && p.presentation?.is_low_stock);
        // Sort: stock=0 (agotado) first, then low stock
        return [...low].sort((a, b) => {
            const aOut = parseFloat(a.presentation?.stock ?? 1) <= 0 ? 0 : 1;
            const bOut = parseFloat(b.presentation?.stock ?? 1) <= 0 ? 0 : 1;
            return aOut - bOut;
        });
    }, [products]);

    // ── Sort handler ──────────────────────────────────────
    const handleSort = (col) => {
        if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
        else { setSortCol(col); setSortDir("asc"); }
    };

    // ── Filtered + sorted list ────────────────────────────
    const filteredProducts = useMemo(() => {
        let list = products.filter(p => {
            if (filterCategory && p.category !== filterCategory) return false;
            if (searchText) {
                const q = searchText.toLowerCase();
                if (!p.name.toLowerCase().includes(q) && !(p.description || "").toLowerCase().includes(q)) return false;
            }
            const st = stockStatus(p).state;
            if (stockFilter === "ok" && st !== "ok") return false;
            if (stockFilter === "low" && st !== "low") return false;
            if (stockFilter === "crit" && st !== "crit") return false;
            return true;
        });

        list.sort((a, b) => {
            let va, vb;
            if (sortCol === "name") {
                va = a.name.toLowerCase(); vb = b.name.toLowerCase();
            } else if (sortCol === "stock") {
                va = parseFloat((a.presentation || {}).stock ?? 0) || 0;
                vb = parseFloat((b.presentation || {}).stock ?? 0) || 0;
            } else if (sortCol === "price") {
                va = parseFloat((a.presentation || {}).sale_price ?? 0) || 0;
                vb = parseFloat((b.presentation || {}).sale_price ?? 0) || 0;
            } else if (sortCol === "value") {
                const aP = a.presentation || {};
                va = (parseFloat(aP.sale_price ?? 0) || 0) * (parseFloat(aP.stock ?? 0) || 0);
                const bP = b.presentation || {};
                vb = (parseFloat(bP.sale_price ?? 0) || 0) * (parseFloat(bP.stock ?? 0) || 0);
            } else if (sortCol === "cat") {
                va = a.category; vb = b.category;
            } else if (sortCol === "status") {
                const order = { crit: 0, low: 1, ok: 2 };
                va = order[stockStatus(a).state]; vb = order[stockStatus(b).state];
            } else return 0;
            if (va < vb) return sortDir === "asc" ? -1 : 1;
            if (va > vb) return sortDir === "asc" ? 1 : -1;
            return 0;
        });
        return list;
    }, [products, filterCategory, searchText, stockFilter, sortCol, sortDir]);

    const filteredTotalVal = useMemo(() =>
        filteredProducts.reduce((acc, p) => {
            const pres = p.presentation || {};
            return acc + (parseFloat(pres.sale_price ?? 0) || 0) * (parseFloat(pres.stock ?? 0) || 0);
        }, 0),
        [filteredProducts]
    );

    // ── Preview ajuste de stock (R1 + R2) ─────────────────
    const previewStock = () => {
        if (!adjustingProduct || !adjustForm.quantity) return null;
        const qty = parseFloat(adjustForm.quantity) || 0;
        const current = parseFloat((adjustingProduct.presentation || {}).stock ?? 0) || 0;
        if (adjustForm.movement_type === "in") return current + qty;
        if (adjustForm.movement_type === "out") return Math.max(current - qty, 0);
        if (adjustForm.movement_type === "adjustment") return qty;
        return null;
    };

    // ── Handlers ──────────────────────────────────────────
    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormErrors({});
        if (!form.name.trim()) { toast.error("El nombre es obligatorio"); return; }
        setSaving(true);
        try {
            const payload = buildProductPayload(form);
            const p = editing ? updateProduct(editing.id, payload) : createProduct(payload);
            await toast.promise(p, {
                loading: editing ? 'Actualizando producto...' : 'Creando producto...',
                success: editing ? 'Producto actualizado' : 'Producto creado',
                error: (err) => {
                    const data = err.response?.data;
                    if (data && typeof data === "object" && !Array.isArray(data) && !data.detail) {
                        return "Revisa los campos con errores";
                    }
                    return apiError(err, "Error al guardar");
                }
            });
            await loadAll();
            closeProductModal();
        } catch (err) {
            const data = err.response?.data;
            if (data && typeof data === "object" && !Array.isArray(data)) {
                setFormErrors(data);
                toast.error("Revisa los campos con errores.");
            }
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id) => {
        const ok = await confirm({ message: "¿Eliminar este producto del inventario?", confirmText: "Eliminar", dangerMode: true });
        if (!ok) return;
        try {
            await toast.promise(deleteProduct(id), {
                loading: 'Eliminando...',
                success: 'Producto eliminado',
                error: (err) => err.response?.data?.detail || "No se puede eliminar: tiene movimientos asociados"
            });
            await loadAll();
        } catch (err) {
        }
    };

    const handleAdjust = async (e) => {
        e.preventDefault();
        if (!adjustForm.quantity || parseFloat(adjustForm.quantity) <= 0) {
            toast.error("La cantidad debe ser mayor a 0"); return;
        }
        setSaving(true);
        try {
            await toast.promise(adjustStock(adjustingProduct.id, { ...adjustForm, quantity: parseFloat(adjustForm.quantity) }), {
                loading: 'Ajustando stock...',
                success: 'Stock ajustado correctamente',
                error: (err) => apiError(err, "Error al ajustar")
            });
            await loadAll();
            closeAdjustModal();
        } catch (err) {
        } finally {
            setSaving(false);
        }
    };

    // openEdit: mapear product.presentation.* al estado plano del form (R1)
    const openEdit = (product, e) => {
        e?.stopPropagation();
        const pres = product.presentation || {};
        setEditing(product);
        setForm({
            name: product.name,
            internal_code: product.internal_code || "",
            description: product.description || "",
            category: product.category || "other",
            requires_prescription: product.requires_prescription || false,
            base_unit: pres.base_unit || "unit",
            sale_price: pres.sale_price || "",
            stock: pres.stock || "",
            min_stock: pres.min_stock || "",
        });
        setFormErrors({});
        setShowProductModal(true);
    };

    const openAdjust = (product, e) => {
        e?.stopPropagation();
        setAdjustingProduct(product);
        setAdjustForm(EMPTY_ADJUST);
        setShowAdjustModal(true);
    };

    const closeProductModal = () => {
        setShowProductModal(false); setEditing(null);
        setForm(EMPTY_PRODUCT); setFormErrors({});
    };
    const closeAdjustModal = () => {
        setShowAdjustModal(false); setAdjustingProduct(null);
        setAdjustForm(EMPTY_ADJUST);
    };

    if (initializing || loading) return (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
            <p style={{ color: "var(--c-text-3)", fontSize: "13px" }}>Cargando...</p>
        </div>
    );

    // ── Render ────────────────────────────────────────────
    return (
        <div>
            {/* ── Page header ── */}
            <div className={s.phead}>
                <div>
                    <div className={s.ptag}>Control de stock</div>
                    <h1 className={s.ptitle}>Inventario</h1>
                    <p className={s.psub}>Productos, medicamentos y suministros de la clínica</p>
                </div>
                {canManage && (
                    <div className={s.pacts}>
                        <button
                            className={s.btnPrime}
                            onClick={() => { setEditing(null); setForm(EMPTY_PRODUCT); setFormErrors({}); setShowProductModal(true); }}
                        >
                            <Icon.Plus s={13} />
                            Nuevo Producto
                        </button>
                    </div>
                )}
            </div>

            {/* ── Stats ── */}
            <div className={s.stats}>
                <div className={`${s.sc} ${s.scG}`}>
                    <div className={`${s.scIco} ${s.scIcoG}`}>
                        <Icon.Package s={13} c="var(--c-primary-dark)" />
                    </div>
                    <div className={s.scVal}>{metrics.total}</div>
                    <div className={s.scLbl}>Total productos</div>
                </div>
                <div className={`${s.sc} ${s.scB}`}>
                    <div className={`${s.scIco} ${s.scIcoB}`}>
                        <Icon.Syringe s={13} c="#3b82f6" />
                    </div>
                    <div className={s.scVal}>{metrics.medications}</div>
                    <div className={s.scLbl}>Medicamentos</div>
                </div>
                <div className={`${s.sc} ${s.scA}`}>
                    <div className={`${s.scIco} ${s.scIcoA}`}>
                        <Icon.AlertTriangle s={13} c="#f59e0b" />
                    </div>
                    <div className={`${s.scVal} ${metrics.lowStock > 0 ? s.scValAm : ""}`}>{metrics.lowStock}</div>
                    <div className={s.scLbl}>Stock bajo</div>
                </div>
                <div className={`${s.sc} ${s.scR}`}>
                    <div className={`${s.scIco} ${s.scIcoR}`}>
                        <Icon.Clock s={13} c="#ef4444" />
                    </div>
                    <div className={`${s.scVal} ${metrics.outOfStock > 0 ? s.scValRe : ""}`}>{metrics.outOfStock}</div>
                    <div className={s.scLbl}>Sin stock</div>
                </div>
                <div className={`${s.sc} ${s.scV}`}>
                    <div className={`${s.scIco} ${s.scIcoV}`}>
                        <Icon.TrendUp s={13} c="#7c3aed" />
                    </div>
                    <div className={s.scVal} style={{ fontSize: "18px" }}>
                        ${fmtCur(metrics.totalVal)}
                    </div>
                    <div className={s.scLbl}>Valor en stock</div>
                </div>
            </div>

            {/* ── Alert bar ── */}
            {!alertDismissed && alertProducts.length > 0 && (
                <div className={s.alertBar}>
                    <Icon.AlertTriangle s={14} />
                    <span>
                        <strong>{alertProducts.length} producto{alertProducts.length !== 1 ? "s" : ""}</strong> requieren atención:{" "}
                        {alertProducts.slice(0, 3).map(p => p.name.split(" ").slice(0, 2).join(" ")).join(", ")}
                        {alertProducts.length > 3 ? "…" : ""}.
                    </span>
                    <button onClick={() => setAlertDismissed(true)} style={{ display: "flex", alignItems: "center" }}>
                        <Icon.X s={14} />
                    </button>
                </div>
            )}

            {/* ── Toolbar ── */}
            <div className={s.toolbar}>
                <div className={s.tsearch}>
                    <Icon.Search s={13} />
                    <input
                        type="text"
                        placeholder="Buscar producto..."
                        value={searchText}
                        onChange={e => setSearchText(e.target.value)}
                    />
                </div>
                <div className={s.tsel}>
                    <Icon.Sliders s={13} />
                    <select value={stockFilter} onChange={e => setStockFilter(e.target.value)}>
                        <option value="">Todo el stock</option>
                        <option value="ok">Normal</option>
                        <option value="low">Stock bajo</option>
                        <option value="crit">Sin stock</option>
                    </select>
                </div>
                <div className={s.viewTog}>
                    <button className={`${s.vt} ${viewMode === "table" ? s.vtOn : ""}`} title="Tabla" onClick={() => setViewMode("table")}>
                        <Icon.Rows s={14} />
                    </button>
                    <button className={`${s.vt} ${viewMode === "grid" ? s.vtOn : ""}`} title="Cuadrícula" onClick={() => setViewMode("grid")}>
                        <Icon.Grid s={14} />
                    </button>
                </div>
                <span className={s.ctLbl}>{filteredProducts.length} producto{filteredProducts.length !== 1 ? "s" : ""}</span>
            </div>

            {/* ── Category chips ── */}
            <div className={s.chipRow}>
                {[
                    { value: "", label: "Todos" },
                    { value: "medication", label: "Medicamentos" },
                    { value: "food", label: "Alimentos" },
                    { value: "accessory", label: "Accesorios" },
                    { value: "other", label: "Otros" },
                ].map(cat => (
                    <button
                        key={cat.value}
                        className={`${s.chip} ${filterCategory === cat.value ? s.chipOn : ""}`}
                        onClick={() => setFilterCategory(cat.value)}
                    >
                        {cat.label}
                    </button>
                ))}
            </div>

            {/* ── Contenido: tabla o grid ── */}
            {filteredProducts.length === 0 ? (
                <div className={s.listEmpty}>
                    <span style={{ display: "block", textAlign: "center", opacity: 0.18 }}>
                        <Icon.Frown s={32} />
                    </span>
                    <p>{searchText ? `Sin resultados para "${searchText}"` : "No hay productos registrados"}</p>
                </div>
            ) : viewMode === "table" ? (
                <div className={s.tableWrap}>
                    <table className={s.table}>
                        <thead>
                            <tr>
                                <SortHeader col="name" label="Producto" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                                <SortHeader col="cat" label="Categoría" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                                <SortHeader col="stock" label="Stock" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                                <SortHeader col="status" label="Estado" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                                <SortHeader col="price" label="Precio unit." sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="right" />
                                <SortHeader col="value" label="Valor en stock" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="right" />
                                {canManage && <th className={s.th}>Acciones</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {filteredProducts.map(product => {
                                // R1: acceso defensivo a presentation
                                const pres = product.presentation || {};
                                const stockVal = parseFloat(pres.stock ?? 0) || 0;
                                const salePrice = parseFloat(pres.sale_price ?? 0) || 0;
                                // R3: base_unit_display solo para mostrar
                                const unitDisplay = pres.base_unit_display || pres.base_unit || "ud.";
                                const val = salePrice * stockVal;
                                const st = stockStatus(product);
                                return (
                                    <tr key={product.id}>
                                        {/* Producto */}
                                        <td className={s.td}>
                                            <div className={s.prodCell}>
                                                <div className={`${s.prodIco} ${ICO_CLS[product.category] || s.icoOther}`}>
                                                    <CategoryIcon category={product.category} />
                                                </div>
                                                <div>
                                                    <div className={s.prodName}>{product.name}</div>
                                                    {product.internal_code && (
                                                        <div className={s.prodDesc}>{product.internal_code}</div>
                                                    )}
                                                    {product.description && (
                                                        <div className={s.prodDesc}>{product.description}</div>
                                                    )}
                                                    <div style={{ display: "flex", gap: "4px", marginTop: "3px", flexWrap: "wrap" }}>
                                                        {product.requires_prescription && (
                                                            <span className={`${s.badge} ${s.badgePurple}`}>Receta</span>
                                                        )}
                                                        {!product.is_active && (
                                                            <span className={`${s.badge} ${s.badgeGray}`}>Inactivo</span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </td>

                                        {/* Categoría */}
                                        <td className={s.td}>
                                            <span className={`${s.badge} ${BADGE_CLS[product.category] || s.badgeGray}`}>
                                                {CATEGORY_LABELS[product.category] || "Otro"}
                                            </span>
                                        </td>

                                        {/* Stock con mini barra */}
                                        <td className={s.td}>
                                            <div className={s.stockCell}>
                                                <span className={`${s.stockNum} ${st.state === "crit" ? s.stockNumCrit : st.state === "low" ? s.stockNumLow : ""}`}>
                                                    {fmt(stockVal)}
                                                </span>
                                                <span className={s.stockUnit}>{unitDisplay}</span>
                                                <div className={s.miniBar}>
                                                    <div
                                                        className={`${s.miniBarFill} ${st.state === "crit" ? s.barCrit : st.state === "low" ? s.barLow : s.barOk}`}
                                                        style={{ width: `${st.pct}%` }}
                                                    />
                                                </div>
                                            </div>
                                        </td>

                                        {/* Estado pill */}
                                        <td className={s.td}>
                                            <span className={`${s.pill} ${st.state === "crit" ? s.pillCrit : st.state === "low" ? s.pillLow : s.pillOk}`}>
                                                <span className={`${s.pillDot} ${st.state === "crit" ? s.dotCrit : st.state === "low" ? s.dotLow : s.dotOk}`} />
                                                {st.label}
                                            </span>
                                        </td>

                                        {/* Precio unitario */}
                                        <td className={s.td} style={{ textAlign: "right" }}>
                                            {salePrice > 0 ? (
                                                <div className={s.valMain}>${fmtCur(salePrice)}</div>
                                            ) : (
                                                <span style={{ color: "var(--c-text-3)", fontSize: "12px" }}>—</span>
                                            )}
                                            {unitDisplay && salePrice > 0 && (
                                                <div className={s.valSub}>por {unitDisplay}</div>
                                            )}
                                        </td>

                                        {/* Valor en stock */}
                                        <td className={s.td} style={{ textAlign: "right" }}>
                                            {val > 0 ? (
                                                <div className={s.valMain}>${fmtCur(val)}</div>
                                            ) : (
                                                <span style={{ color: "var(--c-text-3)", fontSize: "12px" }}>—</span>
                                            )}
                                        </td>

                                        {/* Acciones */}
                                        {canManage && (
                                            <td className={s.td}>
                                                <div className={s.actCell}>
                                                    <button className={`${s.ab} ${s.abAj}`} onClick={e => openAdjust(product, e)}>Ajustar</button>
                                                    <button className={`${s.ab} ${s.abEd}`} onClick={e => openEdit(product, e)}>Editar</button>
                                                    <button className={`${s.ab} ${s.abDl}`} onClick={e => { e.stopPropagation(); handleDelete(product.id); }}>Eliminar</button>
                                                </div>
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>

                    {/* Footer con totales del filtro actual */}
                    <div className={s.tableFooter}>
                        <span>{filteredProducts.length} de {products.length} productos</span>
                        {filteredTotalVal > 0 && (
                            <span>
                                Valor total (filtrado):{" "}
                                <span className={s.footerTotal}>${fmtCur(filteredTotalVal)}</span>
                            </span>
                        )}
                    </div>
                </div>
            ) : (
                /* ── Grid view ── */
                <div className={s.prodGrid}>
                    {filteredProducts.map(product => {
                        const pres = product.presentation || {};
                        const stockVal = parseFloat(pres.stock ?? 0) || 0;
                        const unitDisplay = pres.base_unit_display || pres.base_unit || "ud.";
                        const st = stockStatus(product);
                        return (
                            <div key={product.id} className={s.pg}>
                                <div className={s.pgTop}>
                                    <div className={`${s.pgIco} ${ICO_CLS[product.category] || s.icoOther}`}>
                                        <CategoryIcon category={product.category} size={18} />
                                    </div>
                                    <span className={`${s.badge} ${BADGE_CLS[product.category] || s.badgeGray}`}>
                                        {CATEGORY_LABELS[product.category] || "Otro"}
                                    </span>
                                </div>
                                <div className={s.pgName}>{product.name}</div>
                                {product.description && <div className={s.pgDesc}>{product.description}</div>}
                                <div className={s.pgStk}>
                                    <span className={`${s.pgStkV} ${st.state === "crit" ? s.stockNumCrit : st.state === "low" ? s.stockNumLow : ""}`}>
                                        {fmt(stockVal)}
                                    </span>
                                    <span className={s.pgStkU}>{unitDisplay}</span>
                                </div>
                                <div className={s.pgBar}>
                                    <div className={`${s.pgBarF} ${st.state === "crit" ? s.barCrit : st.state === "low" ? s.barLow : s.barOk}`} style={{ width: `${st.pct}%` }} />
                                </div>
                                {canManage && (
                                    <div className={s.pgFoot}>
                                        <button className={s.pgAdj} onClick={e => openAdjust(product, e)}>Ajustar</button>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── Modal: Nuevo / Editar Producto ── */}
            {showProductModal && (
                <div className="modal-overlay">
                    <div className="modal modal-md">
                        <div className="modal-header">
                            <h3>{editing ? "Editar Producto" : "Nuevo Producto"}</h3>
                            <button className="modal-close" onClick={closeProductModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 14px" }}>
                                    <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                                        <label className="form-label">NOMBRE *</label>
                                        <input
                                            className="input"
                                            value={form.name}
                                            onChange={e => setForm({ ...form, name: e.target.value })}
                                            placeholder="Ej: Amoxicilina 500mg"
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">CÓDIGO INTERNO</label>
                                        <input
                                            className={`input${formErrors.internal_code ? " input-error" : ""}`}
                                            value={form.internal_code}
                                            onChange={e => setForm({ ...form, internal_code: e.target.value })}
                                            placeholder="Ej: MED-001 (opcional)"
                                        />
                                        {formErrors.internal_code && (
                                            <p style={{ color: "var(--c-danger-text)", fontSize: "11.5px", marginTop: "4px" }}>
                                                {formErrors.internal_code}
                                            </p>
                                        )}
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">CATEGORÍA</label>
                                        <select
                                            className="select-input"
                                            value={form.category}
                                            onChange={e => {
                                                const cat = e.target.value;
                                                const allowed = CATEGORY_UNITS[cat];
                                                const unitValid = !allowed || allowed.includes(form.base_unit);
                                                setForm({ ...form, category: cat, base_unit: unitValid ? form.base_unit : (allowed?.[0] ?? "unit") });
                                            }}
                                        >
                                            <option value="medication">Medicamento</option>
                                            <option value="food">Alimento</option>
                                            <option value="accessory">Accesorio</option>
                                            <option value="other">Otro</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">UNIDAD BASE</label>
                                        {/* R9: mostrar disabled mientras carga, evitar layout shift */}
                                        <select
                                            className="select-input"
                                            value={form.base_unit}
                                            onChange={e => setForm({ ...form, base_unit: e.target.value })}
                                            disabled={!unitsLoaded}
                                        >
                                            {!unitsLoaded && <option value="">Cargando unidades...</option>}
                                            {unitChoices
                                                .filter(u => !CATEGORY_UNITS[form.category] || CATEGORY_UNITS[form.category].includes(u.value))
                                                .map(u => (
                                                    <option key={u.value} value={u.value}>{u.label}</option>
                                                ))
                                            }
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">STOCK ACTUAL</label>
                                        <input
                                            type="number" step="1" min="0" className="input"
                                            value={form.stock}
                                            onChange={e => setForm({ ...form, stock: e.target.value })}
                                            placeholder="0"
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">STOCK MÍNIMO (alerta)</label>
                                        <input
                                            type="number" step="1" min="0" className="input"
                                            value={form.min_stock}
                                            onChange={e => setForm({ ...form, min_stock: e.target.value })}
                                            placeholder="0"
                                        />
                                    </div>
                                    <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                                        <label className="form-label">PRECIO DE VENTA</label>
                                        <input
                                            type="number" step="1" min="0" className="input"
                                            value={form.sale_price}
                                            onChange={e => setForm({ ...form, sale_price: e.target.value })}
                                            placeholder="0"
                                        />
                                        {formErrors.presentation?.sale_price && (
                                            <p style={{ color: "var(--c-danger-text)", fontSize: "11.5px", marginTop: "4px" }}>
                                                {formErrors.presentation.sale_price}
                                            </p>
                                        )}
                                    </div>
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
                                <div className="form-group" style={{ marginBottom: 0 }}>
                                    <label className="checkbox-label">
                                        <input
                                            type="checkbox"
                                            checked={form.requires_prescription}
                                            onChange={e => setForm({ ...form, requires_prescription: e.target.checked })}
                                        />
                                        Requiere receta médica
                                    </label>
                                </div>
                            </form>
                        </div>
                        <div className="modal-footer">
                            <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleSubmit} disabled={saving}>
                                {saving ? "Guardando..." : editing ? "Guardar cambios" : "Crear producto"}
                            </button>
                            <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeProductModal}>
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Modal: Ajuste de Stock ── */}
            {showAdjustModal && adjustingProduct && (
                <div className="modal-overlay">
                    <div className="modal modal-sm">
                        <div className="modal-header">
                            <div>
                                <h3>Ajustar Stock</h3>
                                <p style={{ fontSize: "12.5px", color: "var(--c-text-2)", marginTop: "2px" }}>
                                    {adjustingProduct.name}
                                </p>
                            </div>
                            <button className="modal-close" onClick={closeAdjustModal}><Icon.X s={16} /></button>
                        </div>
                        <div className="modal-body">

                            {/* R1 + R3 en el modal de ajuste */}
                            {(() => {
                                const adjPres = adjustingProduct.presentation || {};
                                const adjStock = parseFloat(adjPres.stock ?? 0) || 0;
                                const adjUnit = adjPres.base_unit_display || adjPres.base_unit || "";
                                const preview = previewStock();
                                return (
                                    <div style={{
                                        background: "var(--c-subtle)", borderRadius: "var(--r-lg)",
                                        padding: "12px 16px", display: "flex", justifyContent: "space-between",
                                        alignItems: "center", marginBottom: "20px",
                                    }}>
                                        <div>
                                            <div style={{ fontSize: "10.5px", color: "var(--c-text-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "3px" }}>
                                                Stock actual
                                            </div>
                                            <div style={{ fontSize: "26px", fontWeight: "800", color: "var(--c-text)", lineHeight: 1 }}>
                                                {fmt(adjStock)}
                                                <span style={{ fontSize: "13px", fontWeight: "500", color: "var(--c-text-2)", marginLeft: "4px" }}>
                                                    {adjUnit}
                                                </span>
                                            </div>
                                        </div>
                                        {preview !== null && (
                                            <>
                                                <div style={{ fontSize: "22px", color: "var(--c-text-3)" }}>→</div>
                                                <div style={{ textAlign: "right" }}>
                                                    <div style={{ fontSize: "10.5px", color: "var(--c-text-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "3px" }}>
                                                        Resultado
                                                    </div>
                                                    <div style={{ fontSize: "26px", fontWeight: "800", color: "var(--c-primary-dark)", lineHeight: 1 }}>
                                                        {fmt(preview)}
                                                        <span style={{ fontSize: "13px", fontWeight: "500", color: "var(--c-text-2)", marginLeft: "4px" }}>
                                                            {adjUnit}
                                                        </span>
                                                    </div>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                );
                            })()}

                            <div className="form-group">
                                <label className="form-label">TIPO DE MOVIMIENTO</label>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "7px" }}>
                                    {[
                                        { value: "in", label: "Entrada", icon: "↑", color: "var(--c-success-text)", bg: "var(--c-success-bg)", border: "var(--c-success-border)" },
                                        { value: "out", label: "Salida", icon: "↓", color: "var(--c-danger-text)", bg: "var(--c-danger-bg)", border: "var(--c-danger-border)" },
                                        { value: "adjustment", label: "Ajuste", icon: "⇌", color: "var(--c-warning-text)", bg: "var(--c-warning-bg)", border: "var(--c-warning-border)" },
                                    ].map(opt => {
                                        const active = adjustForm.movement_type === opt.value;
                                        return (
                                            <button
                                                key={opt.value}
                                                type="button"
                                                onClick={() => setAdjustForm({ ...adjustForm, movement_type: opt.value })}
                                                style={{
                                                    padding: "10px 6px",
                                                    border: `1.5px solid ${active ? opt.border : "var(--c-border)"}`,
                                                    borderRadius: "var(--r-lg)",
                                                    background: active ? opt.bg : "var(--c-surface)",
                                                    cursor: "pointer", transition: "all var(--t)",
                                                    display: "flex", flexDirection: "column", alignItems: "center", gap: "3px",
                                                }}
                                            >
                                                <span style={{ fontSize: "20px", color: active ? opt.color : "var(--c-text-3)", lineHeight: 1 }}>{opt.icon}</span>
                                                <span style={{ fontSize: "11.5px", fontWeight: "600", color: active ? opt.color : "var(--c-text-2)" }}>{opt.label}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                                {adjustForm.movement_type === "adjustment" && (
                                    <p style={{ fontSize: "11.5px", color: "var(--c-text-3)", marginTop: "6px" }}>
                                        El ajuste establece el stock directamente al valor indicado.
                                    </p>
                                )}
                            </div>

                            <div className="form-group">
                                <label className="form-label">
                                    {adjustForm.movement_type === "adjustment" ? "NUEVO STOCK *" : "CANTIDAD *"}
                                </label>
                                <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
                                    <button
                                        type="button" className="btn btn-secondary btn-md"
                                        style={{ width: "38px", padding: 0, fontSize: "20px", fontWeight: "400", flexShrink: 0 }}
                                        onClick={() => setAdjustForm(f => ({ ...f, quantity: Math.max(1, parseFloat(f.quantity) - 1) }))}
                                    >−</button>
                                    <input
                                        type="number" step="1" min="1" className="input"
                                        style={{ textAlign: "center", fontWeight: "700", fontSize: "16px" }}
                                        value={adjustForm.quantity}
                                        onChange={e => setAdjustForm({ ...adjustForm, quantity: e.target.value })}
                                    />
                                    <button
                                        type="button" className="btn btn-secondary btn-md"
                                        style={{ width: "38px", padding: 0, fontSize: "20px", fontWeight: "400", flexShrink: 0 }}
                                        onClick={() => setAdjustForm(f => ({ ...f, quantity: parseFloat(f.quantity) + 1 }))}
                                    >+</button>
                                </div>
                            </div>

                            <div className="form-group" style={{ marginBottom: 0 }}>
                                <label className="form-label">MOTIVO</label>
                                <input
                                    type="text" className="input"
                                    value={adjustForm.reason}
                                    onChange={e => setAdjustForm({ ...adjustForm, reason: e.target.value })}
                                    placeholder="Ej: Compra a proveedor, vencimiento, conteo físico..."
                                />
                            </div>
                        </div>
                        <div className="modal-footer">
                            <button className="btn btn-primary btn-md" style={{ flex: 1 }} onClick={handleAdjust} disabled={saving}>
                                {saving ? "Aplicando..." : "Confirmar ajuste"}
                            </button>
                            <button className="btn btn-secondary btn-md" style={{ flex: 1 }} onClick={closeAdjustModal}>
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Inventory;
