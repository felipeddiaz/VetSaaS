import { Icon } from "../icons";

const STATE_CONFIG = {
  provisional: {
    label: "PROVISIONAL",
    className: "db-badge-provisional",
    icon: null,
  },
  frozen: {
    label: "CERRADO",
    className: "db-badge-frozen",
    icon: null,
  },
  rebuilt: {
    label: "RECOMP.",
    className: "db-badge-rebuilt",
    icon: null,
  },
  live: {
    label: "HOY",
    className: "db-badge-live",
    icon: null,
  },
  missing: {
    label: "SIN DATOS",
    className: "db-badge-missing",
    icon: null,
  },
  corrupt: {
    label: "ERROR",
    className: "db-badge-corrupt",
    icon: Icon.AlertTriangle,
  },
};

const LifecycleBadge = ({ state }) => {
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.missing;
  const IconComp = cfg.icon;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontSize: "9px",
        fontWeight: "700",
        letterSpacing: "0.16em",
        textTransform: "uppercase",
        padding: "2px 7px",
        borderRadius: "var(--r-sm)",
        fontFamily: "var(--font-display)",
        lineHeight: "1.4",
        whiteSpace: "nowrap",
        ...(state === "provisional"
          ? {
              color: "var(--c-warning-text)",
              background: "var(--c-warning-bg)",
              border: "1px solid var(--c-warning-border)",
            }
          : state === "live"
            ? {
                color: "var(--c-success-text)",
                background: "var(--c-success-bg)",
                border: "1px solid var(--c-success-border)",
              }
            : state === "missing"
              ? {
                  color: "var(--c-text-4)",
                  background: "transparent",
                  border: "1px dashed var(--c-border-2)",
                }
              : state === "corrupt"
                ? {
                    color: "var(--c-danger-text)",
                    background: "var(--c-danger-bg)",
                    border: "1px solid var(--c-danger-border)",
                  }
                : {
                    color: "var(--c-text-3)",
                    background: "var(--c-subtle)",
                    border: "1px solid var(--c-border)",
                  }),
      }}
    >
      {IconComp && <IconComp s={10} c="currentColor" />}
      {cfg.label}
    </span>
  );
};

export default LifecycleBadge;
