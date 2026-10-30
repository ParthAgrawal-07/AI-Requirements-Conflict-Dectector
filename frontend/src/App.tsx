import React, { useState, useEffect } from "react";
import { ToastProvider, PageLayout } from "./components/ui";
import { FindingsListPage } from "./pages/FindingsListPage";
import { ConflictReviewPage } from "./pages/ConflictReviewPage";
import { ClarificationPage } from "./pages/ClarificationPage";
import { ComponentShowcasePage } from "./pages/ComponentShowcasePage";
import { UploadPage } from "./pages/UploadPage";
import { RequirementsPage } from "./pages/RequirementsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GraphPage } from "./pages/GraphPage";
import { ReportsPage } from "./pages/ReportsPage";

export default function App() {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    if (typeof window !== "undefined" && window.location.hash) {
      return window.location.hash.replace("#", "") || "/findings";
    }
    return "/findings";
  });

  const [selectedFindingId, setSelectedFindingId] = useState<string>("F-001");

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash) {
        setCurrentPath(hash);
        if (hash.startsWith("/findings/")) {
          const parts = hash.split("/");
          if (parts[2]) {
            setSelectedFindingId(parts[2]);
          }
        }
      }
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigateTo = (path: string) => {
    setCurrentPath(path);
    if (typeof window !== "undefined") {
      window.location.hash = path;
    }
  };

  const handleSelectFinding = (id: string) => {
    setSelectedFindingId(id);
    navigateTo(`/findings/${id}`);
  };

  const handleRequestClarification = (id: string) => {
    setSelectedFindingId(id);
    navigateTo(`/findings/${id}/clarification`);
  };

  const handleBackToReview = (id: string) => {
    setSelectedFindingId(id);
    navigateTo(`/findings/${id}`);
  };

  const handleBackToFindings = () => {
    navigateTo("/findings");
  };

  const renderCurrentView = () => {
    if (currentPath.startsWith("/findings/") && currentPath.endsWith("/clarification")) {
      return (
        <ClarificationPage
          findingId={selectedFindingId}
          onBackToReview={handleBackToReview}
          onBackToFindings={handleBackToFindings}
        />
      );
    }

    if (currentPath.startsWith("/findings/")) {
      return (
        <ConflictReviewPage
          findingId={selectedFindingId}
          onBackToFindings={handleBackToFindings}
          onRequestClarification={handleRequestClarification}
        />
      );
    }

    switch (currentPath) {
      case "/requirements":
        return <RequirementsPage />;
      case "/upload":
        return <UploadPage />;
      case "/dashboard":
        return <DashboardPage />;
      case "/graph":
        return <GraphPage />;
      case "/reports":
        return <ReportsPage />;
      case "/components":
        return <ComponentShowcasePage />;
      case "/findings":
      default:
        return <FindingsListPage onSelectFinding={handleSelectFinding} />;
    }
  };

  return (
    <ToastProvider>
      <PageLayout currentPath={currentPath} onNavigate={navigateTo}>
        {renderCurrentView()}
      </PageLayout>
    </ToastProvider>
  );
}
