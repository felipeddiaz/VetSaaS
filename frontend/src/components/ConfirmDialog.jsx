import { createContext, useContext, useState, useRef, useCallback } from "react";

const ConfirmContext = createContext(null);

// ── Visual dialog ──────────────────────────────────────────────────────────────
function ConfirmDialog({ title, message, confirmText, dangerMode, onConfirm, onCancel }) {
    return (
        <div className="modal-overlay" onClick={onCancel}>
            <div className="modal modal-sm" onClick={e => e.stopPropagation()}>
                {title && (
                    <div className="modal-header">
                        <h3>{title}</h3>
                    </div>
                )}
                <div className="modal-body" style={{ paddingTop: title ? "16px" : "24px" }}>
                    <p style={{ color: "var(--c-text-2)", fontSize: "14px", lineHeight: "1.55", margin: 0 }}>
                        {message}
                    </p>
                </div>
                <div className="modal-footer">
                    <button
                        className="btn btn-secondary btn-md"
                        style={{ flex: 1 }}
                        onClick={onCancel}
                    >
                        Cancelar
                    </button>
                    <button
                        className={`btn btn-md ${dangerMode ? "btn-danger" : "btn-primary"}`}
                        style={{ flex: 1 }}
                        onClick={onConfirm}
                        autoFocus
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Provider ───────────────────────────────────────────────────────────────────
export function ConfirmProvider({ children }) {
    const [dialog, setDialog] = useState(null);
    const resolveRef = useRef(null);

    const confirm = useCallback(({
        message,
        title,
        confirmText = "Confirmar",
        dangerMode = false,
    }) => {
        return new Promise((resolve) => {
            resolveRef.current = resolve;
            setDialog({ message, title, confirmText, dangerMode });
        });
    }, []);

    const handleConfirm = () => { resolveRef.current?.(true);  setDialog(null); };
    const handleCancel  = () => { resolveRef.current?.(false); setDialog(null); };

    return (
        <ConfirmContext.Provider value={confirm}>
            {children}
            {dialog && (
                <ConfirmDialog
                    {...dialog}
                    onConfirm={handleConfirm}
                    onCancel={handleCancel}
                />
            )}
        </ConfirmContext.Provider>
    );
}

// ── Hook ───────────────────────────────────────────────────────────────────────
// Uso: const confirm = useConfirm()
//      const ok = await confirm({ message: "...", dangerMode: true })
export function useConfirm() {
    return useContext(ConfirmContext);
}
