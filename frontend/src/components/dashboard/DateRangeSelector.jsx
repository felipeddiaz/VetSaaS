import { Icon } from "../icons";

const PRESETS = [
  { key: "day", label: "Día" },
  { key: "week", label: "Semana" },
  { key: "month", label: "Mes" },
];

const MONTHS_F = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function fmt(d) {
  return `${d.getDate()} ${MONTHS_F[d.getMonth()]}`;
}

function getMonday(d) {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function dayRange(today) {
  return { from: new Date(today), to: new Date(today) };
}

function weekRange(today) {
  const mon = getMonday(today);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  return { from: mon, to: sun > today ? today : sun };
}

function monthRange(today) {
  const first = new Date(today.getFullYear(), today.getMonth(), 1);
  return { from: first, to: today };
}

function getRange(preset, today) {
  switch (preset) {
    case "day": return dayRange(today);
    case "week": return weekRange(today);
    case "month": return monthRange(today);
    default: return dayRange(today);
  }
}

const DateRangeSelector = ({ range, preset, onRangeChange, onPresetChange }) => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const canGoNext = range ? range.to.getTime() < today.getTime() : false;
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(today.getDate() - 30);
  const canGoPrev = range ? range.from.getTime() > thirtyDaysAgo.getTime() : true;

  const handlePreset = (key) => {
    onPresetChange(key);
    onRangeChange(getRange(key, today));
  };

  const handlePrev = () => {
    if (!range || !canGoPrev) return;
    let newFrom, newTo;
    switch (preset) {
      case "day":
        newFrom = new Date(range.from);
        newFrom.setDate(newFrom.getDate() - 1);
        newTo = new Date(newFrom);
        break;
      case "week":
        newTo = new Date(range.from);
        newTo.setDate(newTo.getDate() - 1);
        newFrom = getMonday(newTo);
        break;
      case "month":
        newTo = new Date(range.from);
        newTo.setDate(0); // last day of previous month
        newFrom = new Date(newTo.getFullYear(), newTo.getMonth(), 1);
        break;
      default:
        return;
    }
    if (newFrom < thirtyDaysAgo) return;
    onRangeChange({ from: newFrom, to: newTo });
  };

  const handleNext = () => {
    if (!range || !canGoNext) return;
    let newFrom, newTo;
    switch (preset) {
      case "day":
        newFrom = new Date(range.from);
        newFrom.setDate(newFrom.getDate() + 1);
        newTo = new Date(newFrom);
        break;
      case "week":
        newFrom = new Date(range.to);
        newFrom.setDate(newFrom.getDate() + 1);
        newTo = new Date(newFrom);
        newTo.setDate(newFrom.getDate() + 6);
        break;
      case "month": {
        const m = range.to.getMonth() + 1;
        const y = range.to.getFullYear();
        newFrom = new Date(y, m, 1);
        newTo = new Date(y, m + 1, 0);
        break;
      }
      default:
        return;
    }
    if (newTo > today) {
      newTo = new Date(today);
    }
    onRangeChange({ from: newFrom, to: newTo });
  };

  const rangeLabel = range ? `${fmt(range.from)} – ${fmt(range.to)}` : "";

  return (
    <div className="db-range">
      <button
        className="db-range-arrow"
        onClick={handlePrev}
        disabled={!canGoPrev}
        title={!canGoPrev ? "Límite: 30 días atrás" : "Anterior"}
      >
        <Icon.ChevronLeft s={15} c={canGoPrev ? "var(--c-text-2)" : "var(--c-text-4)"} />
      </button>

      <div className="db-range-presets">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            className={`db-range-preset${preset === p.key ? " db-range-preset-active" : ""}`}
            onClick={() => handlePreset(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <button
        className="db-range-arrow"
        onClick={handleNext}
        disabled={!canGoNext}
        title={!canGoNext ? "Ya estás en el rango actual" : "Siguiente"}
      >
        <Icon.ChevronRight s={15} c={canGoNext ? "var(--c-text-2)" : "var(--c-text-4)"} />
      </button>

      <span className="db-range-label">{rangeLabel}</span>
    </div>
  );
};

export default DateRangeSelector;
