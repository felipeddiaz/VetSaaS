export function HeroPanel() {
  return (
    <div className="hero-panel">
      <div className="eyebrow">Plataforma Veterinaria</div>
      <h1 className="headline">
        Gestiona tu clínica con <em>precisión</em> y <em>empatía</em>.
      </h1>
      <p className="hero-sub">
        La herramienta definitiva para profesionales que buscan optimizar su tiempo y mejorar el cuidado de sus pacientes.
      </p>

      <div className="features">
        {[
          'Control de citas y recordatorios automáticos',
          'Historiales clínicos digitales centralizados',
          'Gestión de inventario y facturación ágil'
        ].map((feat, i) => (
          <div key={i} className="feature-item">
            <div className="bullet" />
            {feat}
          </div>
        ))}
      </div>
    </div>
  );
}
