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

  return (
    <div className="side-panel">
      <div className="side-title">Stock crítico</div>
      {alerts.slice(0, 5).map((a, i) => (
        <div key={i} className="sa-item">
          <span className={`sa-dot ${a.severity === "critical" ? "sa-critical" : "sa-warning"}`} />
          <div className="sa-body">
            <span className="sa-name">{a.product_name}</span>
            <span className="sa-meta">
              {a.presentation_name} · Stock: {a.stock} / Mín: {a.min_stock}
            </span>
          </div>
        </div>
      ))}
      <button
        className="side-link-btn"
        onClick={() => navigate("/inventory")}
      >
        Ver inventario →
      </button>
    </div>
  );
}
