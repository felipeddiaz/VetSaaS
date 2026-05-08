import { useState } from "react";
import { loginRequest, getMe } from "../auth/login";
import { useAuth } from "../auth/authContext";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

export function useLoginForm() {
    const { login, setUserData } = useAuth();
    const navigate = useNavigate();

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [remember, setRemember] = useState(true);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        if (e) e.preventDefault();
        setLoading(true);
        try {
            const data = await loginRequest(username, password);
            const userData = await getMe(data.access);
            login(data.access, data.refresh);
            setUserData(userData);
            navigate("/");
        } catch (err) {
            if (err.response?.status === 401) {
                toast.error("Usuario o contraseña incorrectos.");
            } else {
                toast.error("Error de conexión. Verifica tu internet e intenta de nuevo.");
            }
        } finally {
            setLoading(false);
        }
    };

    return {
        username,
        setUsername,
        password,
        setPassword,
        remember,
        setRemember,
        loading,
        handleSubmit
    };
}
