import api from "./client";

export const getAppointments = async (token, filters = {}) => {
    const params = new URLSearchParams(filters).toString();
    const url = params ? `appointments/?${params}` : "appointments/";
    const res = await api.get(url);
    return res.data;
};

export const createAppointment = async (token, data) => {
    const res = await api.post("appointments/", data);
    return res.data;
};

export const updateAppointment = async (token, id, data) => {
    const res = await api.put(`appointments/${id}/`, data);
    return res.data;
};

export const updateAppointmentStatus = async (token, id, status) => {
    const res = await api.patch(`appointments/${id}/status/`, { status });
    return res.data;
};

export const deleteAppointment = async (token, id) => {
    const res = await api.delete(`appointments/${id}/`);
    return res.data;
};

export const walkInAppointment = async (token, data) => {
    const res = await api.post("appointments/walk-in/", data);
    return res.data;
};

export const getAppointmentHistory = async (id) => {
    const res = await api.get(`appointments/${id}/history/`);
    return res.data;
};

export const assignPatient = async (id, petId) => {
    const res = await api.patch(`appointments/${id}/assign-patient/`, { pet: petId });
    return res.data;
};

export const createAppointmentWithPatient = async (data) => {
    const res = await api.post("appointments/create-with-patient/", data);
    return res.data;
};
