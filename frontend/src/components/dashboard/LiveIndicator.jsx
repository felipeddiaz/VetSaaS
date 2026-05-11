const LiveIndicator = ({ show = true, s = 6 }) => {
  if (!show) return null;

  return (
    <>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "5px",
          fontFamily: "var(--font-display)",
          fontSize: "9px",
          fontWeight: "700",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--c-success-text)",
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: s,
            height: s,
            borderRadius: "50%",
            background: "var(--c-success-text)",
            flexShrink: 0,
            animation: "dbPulse 1.8s ease-out infinite",
          }}
        />
        EN VIVO
      </span>
      <style>{`
        @keyframes dbPulse {
          0%   { box-shadow: 0 0 0 0 rgba(26,92,58,0.55); }
          70%  { box-shadow: 0 0 0 8px rgba(26,92,58,0); }
          100% { box-shadow: 0 0 0 0 rgba(26,92,58,0); }
        }
      `}</style>
    </>
  );
};

export default LiveIndicator;
