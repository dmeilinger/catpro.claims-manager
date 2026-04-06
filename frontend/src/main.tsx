import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AppLayout } from "@/components/layout/AppLayout";
import { Claims } from "@/pages/Claims";
import { InboxPage } from "@/pages/Inbox";
import { AdminSettings } from "@/pages/admin/Settings";
import { Polling } from "@/pages/admin/Polling";
import { Testing } from "@/pages/admin/Testing";
import { EmailHistory } from "@/pages/admin/EmailHistory";
import "./index.css";

// Dashboard brings in Recharts (~500 kB) — lazy-load so it splits into its own chunk
const Dashboard = lazy(() =>
  import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard }))
);

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={null}>
            <Dashboard />
          </Suspense>
        ),
      },
      { path: "claims", element: <Claims /> },
      { path: "inbox", element: <InboxPage /> },
      // Legacy redirect
      { path: "settings", element: <Navigate to="/admin/settings" replace /> },
      {
        path: "admin",
        children: [
          { index: true, element: <Navigate to="/admin/settings" replace /> },
          { path: "settings", element: <AdminSettings /> },
          { path: "polling", element: <Polling /> },
          { path: "testing", element: <Testing /> },
          { path: "email-history", element: <EmailHistory /> },
        ],
      },
      {
        path: "health",
        element: (
          <div className="text-muted-foreground">
            System Health — coming soon
          </div>
        ),
      },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
);
