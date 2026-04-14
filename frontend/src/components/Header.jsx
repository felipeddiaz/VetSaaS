import { useAuth } from "../auth/authContext";

const Header = () => {
    const { user, initializing } = useAuth();

    if (initializing) {
        return null;
    }

    return (
        <header style={{
            height: "60px",
            backgroundColor: "#fff",
            borderBottom: "1px solid #e0e0e0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 30px",
        }}>
            <div>
                <h1 style={{ margin: 0, fontSize: "1.5rem", color: "#333" }}>
                    Dashboard
                </h1>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "15px" }}>
                <span style={{ color: "#666" }}>
                    {user?.username}
                </span>

                <span style={{
                    padding: "5px 12px",
                    backgroundColor: user?.role === "ADMIN" ? "#e94560" : "#4ecca3",
                    color: "white",
                    borderRadius: "20px",
                    fontSize: "0.8rem",
                }}>
                    {user?.role}
                </span>
            </div>
        </header>
    );
};

export default Header;