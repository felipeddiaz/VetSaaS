import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

export default function SearchSelect({
    id,
    name,
    value,
    onChange,
    onSearch,
    placeholder = "Buscar...",
    disabled = false,
    prefetchOnFocus = true,
    defaultQuery = "",
    maxSuggestions = 5,
}) {
    const autoId = useId();
    const inputId = id || `search-select-${autoId}`;
    const listboxId = `${inputId}-listbox`;
    const [inputVal, setInputVal]   = useState(value?.label ?? "");
    const [results,  setResults]    = useState([]);
    const [open,     setOpen]       = useState(false);
    const [loading,  setLoading]    = useState(false);

    const wrapperRef = useRef(null);
    const debounceRef = useRef(null);
    const reqId = useRef(0);
    const lastQueryRef = useRef(null);

    // Sync input text when parent resets value externally
    useEffect(() => {
        setInputVal(value?.label ?? "");
        if (!value) {
            setResults([]);
            setOpen(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value?.id]);

    // Close on outside click
    useEffect(() => {
        function handleMouseDown(e) {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", handleMouseDown);
        return () => document.removeEventListener("mousedown", handleMouseDown);
    }, []);

    function runSearch(q) {
        if (lastQueryRef.current === q && results.length > 0) {
            setOpen(true);
            return;
        }
        if (debounceRef.current) clearTimeout(debounceRef.current);

        setLoading(true);
        setOpen(true);

        debounceRef.current = setTimeout(() => {
            const id = ++reqId.current;
            onSearch(q)
                .then(data => {
                    if (reqId.current !== id) return;
                    setResults(Array.isArray(data) ? data.slice(0, maxSuggestions) : []);
                    lastQueryRef.current = q;
                    setLoading(false);
                })
                .catch(() => {
                    if (reqId.current !== id) return;
                    toast.error("Error al buscar");
                    setResults([]);
                    lastQueryRef.current = null;
                    setLoading(false);
                });
        }, 250);
    }

    function handleInputChange(e) {
        const q = e.target.value;
        setInputVal(q);

        if (!q.trim()) {
            if (prefetchOnFocus) {
                runSearch(defaultQuery);
            } else {
                setResults([]);
                setOpen(false);
                setLoading(false);
            }
            return;
        }

        runSearch(q);
    }

    function handleSelect(item) {
        setInputVal(item.label);
        setResults([]);
        lastQueryRef.current = null;
        setOpen(false);
        onChange(item);
    }

    function handleClear(e) {
        e.stopPropagation();
        if (debounceRef.current) clearTimeout(debounceRef.current);
        reqId.current++;
        setInputVal("");
        setResults([]);
        setOpen(false);
        setLoading(false);
        onChange(null);
    }

    function handleKeyDown(e) {
        if (e.key === "Escape") setOpen(false);
    }

    function handleFocus() {
        if (disabled) return;
        if (prefetchOnFocus && results.length === 0 && !loading) {
            runSearch(defaultQuery);
            return;
        }
        if (results.length > 0) setOpen(true);
    }

    const showClear = !disabled && value !== null && value !== undefined;

    return (
        <div ref={wrapperRef} style={{ position: "relative", width: "100%" }}>
            <div style={{ position: "relative" }}>
                <input
                    id={inputId}
                    name={name || inputId}
                    className="input"
                    value={inputVal}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    onFocus={handleFocus}
                    placeholder={placeholder}
                    disabled={disabled}
                    style={{ paddingRight: showClear ? "28px" : undefined, width: "100%", boxSizing: "border-box" }}
                    autoComplete="off"
                    role="combobox"
                    aria-expanded={open}
                    aria-controls={listboxId}
                />
                {showClear && (
                    <button
                        type="button"
                        onClick={handleClear}
                        style={{
                            position: "absolute", right: "8px", top: "50%", transform: "translateY(-50%)",
                            background: "none", border: "none", cursor: "pointer",
                            color: "var(--c-text-3)", fontSize: "16px", lineHeight: 1,
                            padding: "0 2px", display: "flex", alignItems: "center",
                        }}
                        tabIndex={-1}
                    >
                        ×
                    </button>
                )}
            </div>

            {open && (
                <div
                    id={listboxId}
                    role="listbox"
                    style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
                    zIndex: 200, background: "var(--c-surface)",
                    border: "1px solid var(--c-border)", borderRadius: "var(--r-md)",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)", overflow: "hidden",
                    }}>
                    {loading && (
                        <div style={{ padding: "8px 12px", fontSize: "13px", color: "var(--c-text-3)" }}>
                            Buscando...
                        </div>
                    )}
                    {!loading && results.length === 0 && (
                        <div style={{ padding: "8px 12px", fontSize: "13px", color: "var(--c-text-3)" }}>
                            Sin resultados
                        </div>
                    )}
                    {!loading && results.map((item, index) => (
                        <div
                            key={`${item.id ?? "no-id"}-${item.label ?? "no-label"}-${index}`}
                            onMouseDown={() => handleSelect(item)}
                            style={{
                                padding: "8px 12px", fontSize: "13px", cursor: "pointer",
                                color: "var(--c-text)",
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = "var(--c-subtle)"}
                            onMouseLeave={e => e.currentTarget.style.background = ""}
                        >
                            {item.label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
