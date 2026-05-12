const LiveIndicator = ({ show = true }) => {
  if (!show) return null;
  return (
    <span className="live-indicator">
      <span className="live-indicator-dot" />
      EN VIVO
    </span>
  );
};

export default LiveIndicator;
