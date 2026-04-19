import { useState } from "react";

const WHATSAPP_NUMBER = "521XXXXXXXXXX"; // Cambia por tu número con código de país

const FeedbackButton = () => {
    const [open, setOpen] = useState(false);
    const [message, setMessage] = useState("");

    const handleSend = () => {
        const url = `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message || "Quiero reportar un problema en VetSaaS.")}`;
        window.open(url, "_blank", "noopener,noreferrer");
        setOpen(false);
        setMessage("");
    };

    return (
        <>
            {/* Botón flotante */}
            <button
                onClick={() => setOpen(true)}
                title="Reportar un problema"
                style={{
                    position: "fixed",
                    bottom: "24px",
                    right: "24px",
                    zIndex: 1000,
                    width: "44px",
                    height: "44px",
                    borderRadius: "50%",
                    background: "var(--c-primary, #1a4434)",
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 2px 8px rgba(0,0,0,0.22)",
                    color: "#fff",
                    fontSize: "18px",
                }}
            >
                ?
            </button>

            {/* Modal */}
            {open && (
                <div
                    onClick={(e) => e.target === e.currentTarget && setOpen(false)}
                    style={{
                        position: "fixed", inset: 0, zIndex: 1001,
                        backgroundColor: "rgba(0,0,0,0.35)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}
                >
                    <div style={{
                        background: "var(--c-surface, #fbf8f1)",
                        border: "1px solid var(--c-border, #e5e0d8)",
                        borderRadius: "12px",
                        padding: "28px",
                        width: "360px",
                        maxWidth: "90vw",
                    }}>
                        <h3 style={{ margin: "0 0 6px", fontSize: "15px", fontWeight: "700", color: "var(--c-text, #1a1a1a)" }}>
                            Reportar un problema
                        </h3>
                        <p style={{ margin: "0 0 16px", fontSize: "12px", color: "var(--c-text-3, #8a8a7f)" }}>
                            Describe brevemente qué pasó y te contactamos.
                        </p>
                        <textarea
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            placeholder="Ej: Al guardar una cita aparece un error en la pantalla..."
                            rows={4}
                            style={{
                                width: "100%",
                                padding: "10px 12px",
                                borderRadius: "8px",
                                border: "1px solid var(--c-border, #e5e0d8)",
                                background: "var(--c-bg, #f5f1e8)",
                                fontSize: "13px",
                                color: "var(--c-text, #1a1a1a)",
                                resize: "vertical",
                                boxSizing: "border-box",
                                fontFamily: "inherit",
                            }}
                        />
                        <div style={{ display: "flex", gap: "8px", marginTop: "14px", justifyContent: "flex-end" }}>
                            <button
                                onClick={() => setOpen(false)}
                                style={{
                                    padding: "8px 16px",
                                    background: "transparent",
                                    border: "1px solid var(--c-border, #e5e0d8)",
                                    borderRadius: "7px",
                                    fontSize: "13px",
                                    cursor: "pointer",
                                    color: "var(--c-text-2, #3a3a3a)",
                                }}
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSend}
                                style={{
                                    padding: "8px 16px",
                                    background: "#25D366",
                                    border: "none",
                                    borderRadius: "7px",
                                    fontSize: "13px",
                                    fontWeight: "600",
                                    cursor: "pointer",
                                    color: "#fff",
                                }}
                            >
                                Enviar por WhatsApp
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default FeedbackButton;
