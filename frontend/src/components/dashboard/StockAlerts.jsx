import { useNavigate } from "react-router-dom";

export default function StockAlerts({ alerts }) {
  const navigate = useNavigate();

  if (!alerts || alerts.length === 0) {
    return (
      <div className="side-panel">
        <div className="side-title">Stock crítico</div>
        <div className="side-empty-ok">Sin alertas de stock</div>
      </div>
    );
  }

  const critical = alerts.filter((a) => a.severity === "critical");
  const warning  = alerts.filter((a) => a.severity !== "critical");

  return (
    <div className="side-panel">
      <div className="side-title">
        Stock crítico
        {critical.length > 0 && (
          <span style={{
            marginLeft: "auto",
            fontFamily: "var(--font-display)",
            fontSize: "10px",
            fontWeight: "700",
            background: "#fef2f2",
            color: "#991b1b",
            border: "1px solid #fecaca",
            borderRadius: "999px",
            padding: "1px 8px",
            letterSpacing: "0.04em",
          }}>
            {critical.length} agotado{critical.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="sa-list">
        {/* Critical first */}
        {critical.slice(0, 3).map((a, i) => (
          <div key={`c-${i}`} className="sa-item sa-item-critical">
            <div className="sa-sev-bar sa-sev-critical" />
            <div className="sa-body">
              <span className="sa-name">{a.product_name}</span>
              <span className="sa-meta">
                {a.presentation_name} · {a.stock} / mín {a.min_stock}
              </span>
            </div>
            <span className="sa-badge sa-badge-critical">Agotado</span>
          </div>
        ))}

        {/* Warning after */}
        {warning.slice(0, 2).map((a, i) => (
          <div key={`w-${i}`} className="sa-item">
            <div className="sa-sev-bar sa-sev-warning" />
            <div className="sa-body">
              <span className="sa-name">{a.product_name}</span>
              <span className="sa-meta">
                {a.presentation_name} · {a.stock} / mín {a.min_stock}
              </span>
            </div>
            <span className="sa-badge sa-badge-warning">Bajo</span>
          </div>
        ))}
      </div>

      {alerts.length > 5 && (
        <div style={{
          fontFamily: "var(--font-display)",
          fontSize: "10.5px",
          color: "var(--c-text-3)",
          textAlign: "center",
          padding: "6px 0 2px",
        }}>
          +{alerts.length - 5} más
        </div>
      )}

      <button className="side-link-btn" onClick={() => navigate("/inventory")}>
        Ver inventario →
      </button>
    </div>
  );
}
