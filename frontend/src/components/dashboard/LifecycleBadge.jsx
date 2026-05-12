import { Icon } from "../icons";

const STATE_CLASS = {
  provisional: "lc-badge lc-provisional",
  frozen:      "lc-badge lc-frozen",
  rebuilt:     "lc-badge lc-rebuilt",
  live:        "lc-badge lc-live",
  missing:     "lc-badge lc-missing",
  corrupt:     "lc-badge lc-corrupt",
};

const STATE_LABEL = {
  provisional: "PROVISIONAL",
  frozen:      "CERRADO",
  rebuilt:     "RECOMP.",
  live:        "HOY",
  missing:     "SIN DATOS",
  corrupt:     "ERROR",
};

const LifecycleBadge = ({ state }) => {
  const cls   = STATE_CLASS[state] || STATE_CLASS.missing;
  const label = STATE_LABEL[state] || STATE_LABEL.missing;
  const IconComp = state === "corrupt" ? Icon.AlertTriangle : null;

  return (
    <span className={cls}>
      {IconComp && <IconComp s={10} c="currentColor" />}
      {label}
    </span>
  );
};

export default LifecycleBadge;
