import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";

const PrivateRoute = ({ children }) => {
    const { isAuthenticated, initializing } = useAuth();

    if (!initializing && !isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return children;
};

export default PrivateRoute;