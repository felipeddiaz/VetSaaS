import { useState, useRef } from "react";
import { toast } from "sonner";
import { useAuth } from "../auth/authContext";

const DISCORD_WEBHOOK_URL = import.meta.env.VITE_DISCORD_WEBHOOK_URL;

const FeedbackButton = () => {
    const { user } = useAuth();
    const [open, setOpen] = useState(false);
    const [message, setMessage] = useState("");
    const [image, setImage] = useState(null);
    const [sending, setSending] = useState(false);
    const fileInputRef = useRef(null);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 5 * 1024 * 1024) { // Límite 5MB
                toast.error("La imagen es demasiado grande (máx 5MB)");
                return;
            }
            setImage(file);
        }
    };

    const handleSend = async () => {
        if (!message.trim()) {
            toast.error("Por favor, describe el problema.");
            return;
        }

        setSending(true);
        try {
            const formData = new FormData();
            
            const payload = {
                embeds: [
                    {
                        title: "🚀 Nuevo reporte de problema",
                        description: message,
                        color: 16711680,
                        fields: [
                            {
                                name: "👤 Usuario",
                                value: user ? `${user.first_name || ""} ${user.last_name || ""} (@${user.username})` : "Anónimo",
                                inline: true
                            },
                            {
                                name: "🏢 Organización",
                                value: user?.organization_name || user?.organization || "N/A",
                                inline: true
                            },
                            {
                                name: "📍 Página",
                                value: window.location.href,
                                inline: false
                            },
                            {
                                name: "💻 Sistema / Navegador",
                                value: navigator.userAgent.split(') ')[0] + ')',
                                inline: true
                            },
                            {
                                name: "📏 Pantalla",
                                value: `${window.innerWidth}x${window.innerHeight}`,
                                inline: true
                            }
                        ],
                        footer: {
                            text: "SaaSly — Intelligent Diagnostics"
                        },
                        timestamp: new Date().toISOString()
                    }
                ]
            };

            // Si hay imagen, la adjuntamos al FormData
            if (image) {
                formData.append("file", image, image.name);
                // Discord permite referenciar el archivo adjunto en el embed
                payload.embeds[0].image = { url: `attachment://${image.name}` };
            }

            formData.append("payload_json", JSON.stringify(payload));

            const response = await fetch(DISCORD_WEBHOOK_URL, {
                method: "POST",
                body: formData, // fetch maneja el Content-Type automáticamente para FormData
            });

            if (response.ok) {
                toast.success("Reporte enviado correctamente. ¡Gracias!");
                setOpen(false);
                setMessage("");
                setImage(null);
            } else {
                throw new Error();
            }
        } catch (err) {
            toast.error("No se pudo enviar el reporte. Intenta más tarde.");
        } finally {
            setSending(false);
        }
    };

    return (
        <>
            <button
                onClick={() => setOpen(true)}
                title="Reportar un problema"
                style={{
                    position: "fixed", bottom: "24px", right: "24px", zIndex: 1000,
                    width: "44px", height: "44px", borderRadius: "50%",
                    background: "var(--accent, #047857)", border: "none", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.15)", color: "#fff", fontSize: "20px",
                }}
            >
                ?
            </button>

            {open && (
                <div
                    onClick={(e) => e.target === e.currentTarget && setOpen(false)}
                    style={{
                        position: "fixed", inset: 0, zIndex: 1001,
                        backgroundColor: "rgba(0,0,0,0.4)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        backdropFilter: "blur(4px)",
                    }}
                >
                    <div style={{
                        background: "#fff", borderRadius: "16px", padding: "32px",
                        width: "400px", maxWidth: "90vw", boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
                    }}>
                        <h3 style={{ margin: "0 0 8px", fontSize: "18px", fontWeight: "700", color: "#111" }}>
                            ¿Algo no va bien?
                        </h3>
                        <p style={{ margin: "0 0 20px", fontSize: "14px", color: "#666", lineHeight: "1.4" }}>
                            Describe el problema y adjunta una captura si es necesario.
                        </p>
                        
                        <textarea
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            placeholder="Ej: No puedo ver el botón de imprimir en facturas..."
                            rows={4}
                            style={{
                                width: "100%", padding: "14px", borderRadius: "10px",
                                border: "1.5px solid #eee", background: "#fafafa",
                                fontSize: "14px", color: "#111", resize: "none",
                                boxSizing: "border-box", fontFamily: "inherit", outline: "none",
                                transition: "border-color 0.2s"
                            }}
                            onFocus={(e) => e.target.style.borderColor = "var(--accent)"}
                            onBlur={(e) => e.target.style.borderColor = "#eee"}
                        />

                        <div style={{ marginTop: "16px" }}>
                            <input 
                                type="file" 
                                accept="image/*" 
                                onChange={handleFileChange} 
                                ref={fileInputRef} 
                                style={{ display: "none" }} 
                            />
                            <button
                                onClick={() => fileInputRef.current.click()}
                                style={{
                                    display: "flex", alignItems: "center", gap: "8px",
                                    padding: "8px 12px", borderRadius: "8px", border: "1px dashed #ccc",
                                    background: image ? "#f0fdf4" : "transparent",
                                    fontSize: "13px", cursor: "pointer", width: "100%",
                                    color: image ? "#166534" : "#666"
                                }}
                            >
                                {image ? "📸 Imagen adjunta: " + image.name : "📎 Adjuntar captura de pantalla"}
                            </button>
                        </div>

                        <div style={{ display: "flex", gap: "10px", marginTop: "24px" }}>
                            <button
                                onClick={() => setOpen(false)}
                                style={{
                                    flex: 1, padding: "12px", background: "#f5f5f5",
                                    border: "none", borderRadius: "10px", fontSize: "14px",
                                    fontWeight: "600", cursor: "pointer", color: "#666"
                                }}
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSend}
                                disabled={sending}
                                style={{
                                    flex: 2, padding: "12px", background: "#5865F2",
                                    border: "none", borderRadius: "10px", fontSize: "14px",
                                    fontWeight: "600", cursor: "pointer", color: "#fff",
                                    opacity: sending ? 0.7 : 1, display: "flex",
                                    alignItems: "center", justifyContent: "center", gap: "8px"
                                }}
                            >
                                {sending ? "Enviando..." : "Enviar a Soporte"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default FeedbackButton;
