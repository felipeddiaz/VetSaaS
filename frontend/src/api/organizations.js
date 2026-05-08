import api from "./client";

export const getOrgSettings = () =>
    api.get("organizations/settings/").then(r => r.data);

export const updateOrgSettings = (data) =>
    api.patch("organizations/settings/", data).then(r => r.data);
