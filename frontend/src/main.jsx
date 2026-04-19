import React from "react";
import ReactDOM from "react-dom/client";
import * as Sentry from "@sentry/react";
import "./index.css";
import App from "./App";

// Sentry — si VITE_SENTRY_DSN no está definida, init() no hace nada.
// Obtener DSN en https://sentry.io → tu proyecto → Settings → Client Keys
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.2,
    // Propagar traces a requests hacia el backend (dev + prod)
    tracePropagationTargets: [
      "localhost",
      "127.0.0.1",
      /^https:\/\/api\./,  // ajustar al dominio de producción
    ],
  });
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <App />
);