import React from "react";
import {
  PageHeader,
  StatCard,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  ProgressBar,
} from "../components/ui";

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[{ label: "Atlas Customer Portal" }, { label: "Dashboard" }]}
        title="Project Insights & Health"
        description="Requirement conflict metrics, risk indicators, and resolution tracking for Atlas Customer Portal."
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          value="94.2%"
          label="SRS Cohesion"
          description="+1.4% from baseline v1.3"
          trend={{ value: "+1.4% improvement", isPositive: true }}
        />
        <StatCard
          value="6"
          label="Open Issues"
          description="3 pending review"
          valueColor="text-blue-600"
        />
        <StatCard
          value="2"
          label="High Severity"
          description="Action required"
          valueColor="text-red-600"
        />
        <StatCard
          value="83%"
          label="Review Progress"
          description="5 of 6 assessed"
          valueColor="text-emerald-600"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Conflict Severity Distribution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <ProgressBar value={33} label="High Severity (2 issues)" color="amber" showValue />
              <ProgressBar value={50} label="Medium Severity (3 issues)" color="blue" showValue />
              <ProgressBar value={17} label="Low Severity (1 issue)" color="emerald" showValue />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sprint Ownership Overview</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-600 space-y-2">
            <p>Sprint 4 Dashboard and Graph visualization owned by <strong>Dhvani</strong>.</p>
            <p>Sprint 1 UI Component Library foundation provided by <strong>Abhijeet</strong>.</p>
            <p>Detection pipeline and candidate pairs powered by <strong>Heet</strong> and <strong>Keval</strong>.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
