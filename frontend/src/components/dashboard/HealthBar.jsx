const MONTHS_F = [
  "Enero","Febrero","Marzo","Abril","Mayo","Junio",
  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
];

function formatToday() {
  const d       = new Date();
  const dayName = d.toLocaleDateString("es-MX", { weekday: "long" });
  return `${dayName.charAt(0).toUpperCase() + dayName.slice(1)}, ${d.getDate()} de ${MONTHS_F[d.getMonth()]}, ${d.getFullYear()}`;
}

const HealthBar = ({ range }) => {
  const tz      = range?.tz || "";
  const tzShort = tz.includes("/") ? tz.split("/").pop()?.replace("_", " ") : tz;

  return (
    <div className="db-healthbar">
      <div />
      <div className="db-healthbar-right">
        <span>{formatToday()}</span>
        {tzShort && <span className="db-healthbar-tz">{tzShort}</span>}
      </div>
    </div>
  );
};

export default HealthBar;
