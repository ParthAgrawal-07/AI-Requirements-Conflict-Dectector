import React from "react";
import { PageHeader, Card, CardContent, NetworkIcon } from "../components/ui";

export function GraphPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[{ label: "Atlas Customer Portal" }, { label: "Graph" }]}
        title="Requirements Dependency & Conflict Graph"
        description="Interactive visualization of requirement relationships, clusters, and detected conflict edges."
      />

      <Card>
        <CardContent className="p-12 flex flex-col items-center justify-center text-center">
          <div className="w-16 h-16 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
            <NetworkIcon size={32} />
          </div>
          <h3 className="text-base font-semibold text-slate-900 mb-1">
            React Flow Graph Canvas (Sprint 4 US-14)
          </h3>
          <p className="text-xs text-slate-500 max-w-md">
            The dependency graph provides visual topology of cross-cutting requirements. Scaffolded with React Flow dependency already present in package.json.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
