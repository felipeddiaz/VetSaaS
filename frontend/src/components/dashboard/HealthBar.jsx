const MONTHS_F = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function formatToday() {
  const d = new Date();
  const dayName = d.toLocaleDateString("es-MX", { weekday: "long" });
  const day = d.getDate();
  const month = MONTHS_F[d.getMonth()];
  const year = d.getFullYear();
  return `${dayName.charAt(0).toUpperCase() + dayName.slice(1)}, ${day} de ${month}, ${year}`;
}

const HealthBar = ({ range }) => {
  const tz = range?.tz || "";
  const tzShort = tz.includes("/") ? tz.split("/").pop()?.replace("_", " ") : tz;

  return (
    <div className="db-healthbar">
      <div />
      <div className="db-healthbar-right">
        <span>{formatToday()}</span>
        {tzShort && <span style={{ color: "var(--c-text-3)", marginLeft: "6px" }}>{tzShort}</span>}
      </div>
    </div>
  );
};

export default HealthBar;
