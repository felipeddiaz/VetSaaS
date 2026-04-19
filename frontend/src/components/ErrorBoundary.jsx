import { Component } from "react";

class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, info) {
        console.error("[ErrorBoundary]", error, info.componentStack);
    }

    render() {
        if (!this.state.hasError) return this.props.children;

        return (
            <div style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "100vh",
                backgroundColor: "var(--c-bg, #f5f1e8)",
                padding: "40px",
                textAlign: "center",
            }}>
                <div style={{
                    backgroundColor: "var(--c-surface, #fbf8f1)",
                    border: "1px solid var(--c-border, #e5e0d8)",
                    borderRadius: "12px",
                    padding: "40px",
                    maxWidth: "480px",
                    width: "100%",
                }}>
                    <p style={{ fontSize: "32px", margin: "0 0 12px" }}>⚠️</p>
                    <h2 style={{ fontSize: "18px", fontWeight: "700", color: "var(--c-text, #1a1a1a)", margin: "0 0 8px" }}>
                        Algo salió mal
                    </h2>
                    <p style={{ fontSize: "13px", color: "var(--c-text-3, #8a8a7f)", margin: "0 0 24px" }}>
                        Ocurrió un error inesperado. Recarga la página o reporta el problema.
                    </p>
                    <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
                        <button
                            onClick={() => window.location.reload()}
                            style={{
                                padding: "9px 20px",
                                background: "var(--c-primary, #1a4434)",
                                color: "#fff",
                                border: "none",
                                borderRadius: "8px",
                                fontSize: "13px",
                                fontWeight: "600",
                                cursor: "pointer",
                            }}
                        >
                            Recargar página
                        </button>
                        <button
                            onClick={() => this.setState({ hasError: false, error: null })}
                            style={{
                                padding: "9px 20px",
                                background: "transparent",
                                color: "var(--c-text-2, #3a3a3a)",
                                border: "1px solid var(--c-border, #e5e0d8)",
                                borderRadius: "8px",
                                fontSize: "13px",
                                fontWeight: "600",
                                cursor: "pointer",
                            }}
                        >
                            Intentar de nuevo
                        </button>
                    </div>
                </div>
            </div>
        );
    }
}

export default ErrorBoundary;
