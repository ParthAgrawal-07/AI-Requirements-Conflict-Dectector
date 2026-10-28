import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { ToastProvider } from "../components/Toast";
import { AuthProvider, useAuth } from "./auth";
import { createQueryClient } from "./queryClient";
import { routes } from "./routes";
import { RealtimeProvider } from "./socket";

// v7 behaviour now, so the upgrade later changes nothing.
const router = createBrowserRouter(routes, {
  future: { v7_relativeSplatPath: true },
});

function WithRealtime() {
  const { token } = useAuth();
  return (
    <RealtimeProvider token={token}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </RealtimeProvider>
  );
}

export default function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <WithRealtime />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
