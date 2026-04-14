import axios from "axios";

const api = axios.create({
    baseURL: "http://127.0.0.1:8000/api/",
});

export const loginRequest = async (username, password) => {
    const res = await axios.post("http://127.0.0.1:8000/api/token/", {
        username,
        password,
    });

    return res.data;
};

export const getMe = async (token) => {
    const res = await api.get("me/", {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });
    return res.data;
};

export const refreshTokenRequest = async (refreshToken) => {
    const res = await axios.post("http://127.0.0.1:8000/api/token/refresh/", {
        refresh: refreshToken,
    });
    return res.data;
};