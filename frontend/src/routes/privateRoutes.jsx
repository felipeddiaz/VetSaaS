import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";

const PrivateRoute = ({ children }) => {
    const { token, user, initializing } = useAuth();

    if (!initializing && !user) {
        return <Navigate to="/login" replace />;
    }

    return children;
};

export default PrivateRoute;