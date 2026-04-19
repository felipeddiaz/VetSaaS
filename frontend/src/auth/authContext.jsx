import { createContext, useContext, useState, useEffect, useRef, useCallback } from "react";

const AuthContext = createContext();

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
                const res = await fetch("/api/token/refresh/", {
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
            } catch {
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
        }
        if (storedUser) {
            setUser(JSON.parse(storedUser));
        }

        setInitializing(false);

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
    };

    const isAuthenticated = !!token && !!user;

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
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
