import { createContext, useContext, useState, useEffect, useRef, useCallback } from "react";

const AuthContext = createContext();

const rawBase = import.meta.env.VITE_API_URL || "";
const API_BASE = rawBase.endsWith("/") ? rawBase : rawBase + "/";

const REFRESH_BEFORE_EXPIRY_MS = 5 * 60 * 1000; // refrescar 5 min antes de expirar

function getTokenExp(token) {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.exp * 1000; // exp en segundos → ms
    } catch {
        return null;
    }
}

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(null);
    const [user, setUser] = useState(null);
    const [initializing, setInitializing] = useState(true);
    const [permissions, setPermissions] = useState(() => new Set());
    const refreshTimerRef = useRef(null);

    const logout = useCallback(() => {
        if (refreshTimerRef.current) {
            clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = null;
        }
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user");
        setToken(null);
        setUser(null);
        setPermissions(new Set());
    }, []);

    const scheduleTokenRefresh = useCallback((accessToken) => {
        if (refreshTimerRef.current) {
            clearTimeout(refreshTimerRef.current);
        }

        const exp = getTokenExp(accessToken);
        if (!exp) return;

        const delay = Math.max(exp - Date.now() - REFRESH_BEFORE_EXPIRY_MS, 0);

        refreshTimerRef.current = setTimeout(async () => {
            const storedRefresh = localStorage.getItem("refresh_token");
            if (!storedRefresh) {
                logout();
                return;
            }

            try {
                const res = await fetch(`${API_BASE}token/refresh/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ refresh: storedRefresh }),
                });

                if (res.ok) {
                    const data = await res.json();
                    localStorage.setItem("access_token", data.access);
                    setToken(data.access);
                    scheduleTokenRefresh(data.access);
                } else {
                    logout();
                }
            } catch (err) {
                console.error("[Auth] Token refresh failed", err);
                logout();
            }
        }, delay);
    }, [logout]);

    useEffect(() => {
        const storedToken = localStorage.getItem("access_token");
        const storedUser = localStorage.getItem("user");

        if (storedToken) {
            setToken(storedToken);
            scheduleTokenRefresh(storedToken);

            // Refresh user data from server to avoid stale org/role data in localStorage
            fetch(`${API_BASE}me/`, {
                headers: { Authorization: `Bearer ${storedToken}` },
            })
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (data) {
                        localStorage.setItem("user", JSON.stringify(data));
                        setUser(data);
                        setPermissions(Object.freeze(new Set(data.permissions || [])));
                    } else if (storedUser) {
                        const parsed = JSON.parse(storedUser);
                        setUser(parsed);
                        setPermissions(Object.freeze(new Set(parsed.permissions || [])));
                    }
                })
                .catch(() => {
                    if (storedUser) {
                        const parsed = JSON.parse(storedUser);
                        setUser(parsed);
                        setPermissions(Object.freeze(new Set(parsed.permissions || [])));
                    }
                })
                .finally(() => setInitializing(false));
        } else {
            if (storedUser) {
                const parsed = JSON.parse(storedUser);
                setUser(parsed);
                setPermissions(Object.freeze(new Set(parsed.permissions || [])));
            }
            setInitializing(false);
        }

        return () => {
            if (refreshTimerRef.current) {
                clearTimeout(refreshTimerRef.current);
            }
        };
    }, [scheduleTokenRefresh]);

    const login = (accessToken, refreshToken) => {
        localStorage.setItem("access_token", accessToken);
        localStorage.setItem("refresh_token", refreshToken);
        setToken(accessToken);
        scheduleTokenRefresh(accessToken);
    };

    const setUserData = (userData) => {
        localStorage.setItem("user", JSON.stringify(userData));
        setUser(userData);
        setPermissions(Object.freeze(new Set(userData.permissions || [])));
    };

    const isAuthenticated = !!token && !!user;

    const can = useCallback(
        (permCode) => permissions.has(permCode),
        [permissions]
    );

    const canAny = useCallback(
        (codes) => codes.some(code => permissions.has(code)),
        [permissions]
    );

    const canAll = useCallback(
        (codes) => codes.every(code => permissions.has(code)),
        [permissions]
    );

    return (
        <AuthContext.Provider
            value={{
                token,
                user,
                initializing,
                login,
                logout,
                setUserData,
                isAuthenticated,
                permissions,
                can,
                canAny,
                canAll,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
