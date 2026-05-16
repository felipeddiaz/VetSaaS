import { useNavigate } from "react-router-dom";

export default function StockAlerts({ alerts }) {
  const navigate = useNavigate();

  if (!alerts || alerts.length === 0) {
    return (
      <div className="dsp">
        <div className="dsp-head">
          <h3 className="dsp-title">Stock crítico</h3>
        </div>
        <p className="dsp-empty">Sin alertas de stock.</p>
      </div>
    );
  }

  const critical = alerts.filter((a) => a.severity === "critical");
  const warning  = alerts.filter((a) => a.severity !== "critical");

  return (
    <div className="dsp">
      <div className="dsp-head">
        <h3 className="dsp-title">Stock crítico</h3>
        {critical.length > 0 && (
          <span className="badge badge-danger">{critical.length}</span>
        )}
      </div>

      <ul className="dsp-list">
        {critical.slice(0, 3).map((a, i) => (
          <li key={`c-${i}`} className="dsp-item dsp-item-critical">
            <span className="dsp-sev dsp-sev-critical" />
            <div className="dsp-item-body">
              <span className="dsp-item-name">{a.product_name}</span>
              <span className="dsp-item-meta">
                {a.presentation_name} · {a.stock} / mín {a.min_stock}
              </span>
            </div>
            <span className="badge badge-danger">Agotado</span>
          </li>
        ))}
        {warning.slice(0, 2).map((a, i) => (
          <li key={`w-${i}`} className="dsp-item">
            <span className="dsp-sev dsp-sev-warning" />
            <div className="dsp-item-body">
              <span className="dsp-item-name">{a.product_name}</span>
              <span className="dsp-item-meta">
                {a.presentation_name} · {a.stock} / mín {a.min_stock}
              </span>
            </div>
            <span className="badge badge-warning">Bajo</span>
          </li>
        ))}
      </ul>

      {alerts.length > 5 && (
        <p className="dsp-overflow">+{alerts.length - 5} más</p>
      )}

      <button className="btn btn-ghost btn-xs dsp-action" onClick={() => navigate("/inventory")}>
        Ver inventario →
      </button>
    </div>
  );
}
