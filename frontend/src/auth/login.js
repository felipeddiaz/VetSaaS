import api from "../api/client";

export const loginRequest = async (username, password) => {
    const res = await api.post("token/", { username, password });
    return res.data;
};

export const getMe = async (token) => {
    const res = await api.get("me/", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return res.data;
};

export const refreshTokenRequest = async (refreshToken) => {
    const res = await api.post("token/refresh/", { refresh: refreshToken });
    return res.data;
};
