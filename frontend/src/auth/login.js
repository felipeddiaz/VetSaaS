import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL;

export const loginRequest = async (username, password) => {
    const res = await axios.post(`${API_URL}token/`, { username, password });
    return res.data;
};

export const getMe = async (token) => {
    const res = await axios.get(`${API_URL}me/`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    return res.data;
};

export const refreshTokenRequest = async (refreshToken) => {
    const res = await axios.post(`${API_URL}token/refresh/`, { refresh: refreshToken });
    return res.data;
};
