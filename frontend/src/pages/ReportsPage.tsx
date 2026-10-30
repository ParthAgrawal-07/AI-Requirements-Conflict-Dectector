import React from "react";
import {
  PageHeader,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  Button,
  LayersIcon,
  FileTextIcon,
  useToast,
} from "../components/ui";

export function ReportsPage() {
  const toast = useToast();

  const handleDownloadReport = (type: string) => {
    toast.success(`Preparing ${type} export for download...`, "Report Export");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[{ label: "Atlas Customer Portal" }, { label: "Reports" }]}
        title="Multi-Channel Reports & Exports"
        description="Generate audit-ready conflict summaries, open items reports, and stakeholder briefings (Sprint 5 US-16)."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileTextIcon size={18} className="text-blue-600" />
              <CardTitle>Open Conflicts Summary (PDF)</CardTitle>
            </div>
            <CardDescription>
              Executive summary of all active, unresolved requirement contradictions with owner attributions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-slate-500">
              Includes 6 detected findings from baseline v1.4, confidence scores, and pending clarification threads.
            </p>
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleDownloadReport("Conflict Summary PDF")}
            >
              Export PDF Report
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <LayersIcon size={18} className="text-emerald-600" />
              <CardTitle>Requirements Audit Log (CSV)</CardTitle>
            </div>
            <CardDescription>
              Tabular dump of requirement statements, segmentation boundaries, and review decisions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-slate-500">
              Export format compliant with ADR-16 audit standards and EARS template mapping.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleDownloadReport("Audit Log CSV")}
            >
              Export CSV Dataset
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
