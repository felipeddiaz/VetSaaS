import axios from "axios";

const rawBase = import.meta.env.VITE_API_URL;
if (!rawBase) {
    throw new Error("VITE_API_URL no está definida");
}

const api = axios.create({
    baseURL: rawBase.endsWith('/') ? rawBase : rawBase + '/',
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
            localStorage.removeItem("user");
            window.location.href = "/login";
        } else if (error.response?.status >= 500) {
            alert("Error del servidor. Intenta más tarde.");
        }
        return Promise.reject(error);
    }
);

export default api;