import { BrowserRouter, Routes, Route } from "react-router-dom";
import Login from "./pages/login";
import Dashboard from "./pages/dashboard";
import PrivateRoute from "./routes/privateRoutes";
import Pets from "./pages/pets";
import PetDetail from "./pages/petDetail";
import Layout from "./components/Layout";
import { useAuth } from "./auth/authContext";
import { AuthProvider } from "./auth/authContext";
import Staff from "./pages/staff";
import Appointments from "./pages/appointments";
import MedicalRecords from "./pages/medicalRecords";
import Inventory from "./pages/inventory";
import Billing from "./pages/billing";
import Prescriptions from "./pages/prescriptions";
import Config from "./pages/config";
import NotFound from "./pages/notFound";
import ErrorBoundary from "./components/ErrorBoundary";
import FeedbackButton from "./components/FeedbackButton";
import { ConfirmProvider } from "./components/ConfirmDialog";
import { Toaster } from "sonner";

const LoadingScreen = () => (
  <div style={{
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    height: "100vh",
    backgroundColor: "#f5f5f5"
  }}>
    <p>Cargando...</p>
  </div>
);

function AppContent() {
  const { initializing } = useAuth();

  if (initializing) {
    return <LoadingScreen />;
  }

  const wrap = (Component) => (
    <PrivateRoute>
      <Layout>
        <ErrorBoundary>
          <Component />
        </ErrorBoundary>
      </Layout>
    </PrivateRoute>
  );

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={wrap(Dashboard)} />
        <Route path="/pets" element={wrap(Pets)} />
        <Route path="/pets/:id" element={wrap(PetDetail)} />
        <Route path="/staff" element={wrap(Staff)} />
        <Route path="/appointments" element={wrap(Appointments)} />
        <Route path="/medical-records" element={wrap(MedicalRecords)} />
        <Route path="/inventory" element={wrap(Inventory)} />
        <Route path="/billing" element={wrap(Billing)} />
        <Route path="/prescriptions" element={wrap(Prescriptions)} />
        <Route path="/config" element={wrap(Config)} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <FeedbackButton />
    </>
  );
}


function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ConfirmProvider>
          <ErrorBoundary>
            <AppContent />
          </ErrorBoundary>
        </ConfirmProvider>
        <Toaster richColors position="top-right" toastOptions={{ duration: 4000 }} visibleToasts={3} />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
