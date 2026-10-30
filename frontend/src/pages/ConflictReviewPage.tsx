import React, { useState } from "react";
import {
  PageHeader,
  RequirementCard,
  AIExplanationCard,
  StatusBadge,
  Button,
  Textarea,
  Card,
  CardContent,
  CheckIcon,
  XIcon,
  MessageSquareIcon,
  ConfirmDialog,
  useToast,
} from "../components/ui";
import { sampleFindings, FindingDetail } from "../lib/sampleData";

export interface ConflictReviewPageProps {
  findingId: string;
  onBackToFindings: () => void;
  onRequestClarification: (id: string) => void;
}

export function ConflictReviewPage({
  findingId,
  onBackToFindings,
  onRequestClarification,
}: ConflictReviewPageProps) {
  const toast = useToast();
  const finding: FindingDetail =
    sampleFindings.find((f) => f.id === findingId) || sampleFindings[0];

  const [notes, setNotes] = useState(finding.reviewerNotes || "");
  const [currentStatus, setCurrentStatus] = useState<string>(finding.status);
  const [confirmAction, setConfirmAction] = useState<"accept" | "dismiss" | "resolve" | null>(null);

  const handleAction = (action: "accept" | "dismiss" | "resolve") => {
    setConfirmAction(action);
  };

  const executeAction = () => {
    if (!confirmAction) return;

    if (confirmAction === "accept") {
      setCurrentStatus("Accepted");
      toast.success("Conflict confirmed and accepted for resolution.", "Finding Accepted");
    } else if (confirmAction === "dismiss") {
      setCurrentStatus("Dismissed");
      toast.info("Finding marked as dismissed with rationale recorded.", "Finding Dismissed");
    } else if (confirmAction === "resolve") {
      setCurrentStatus("Resolved");
      toast.success("Requirement change agreed and documented.", "Finding Resolved");
    }

    setConfirmAction(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Findings", onClick: onBackToFindings },
          { label: finding.id },
          { label: "Review" },
        ]}
        title={finding.title}
        badge={<StatusBadge status={currentStatus} />}
        description="Compare the source requirements and record a reasoned decision before changing the finding status."
        actions={
          <Button variant="outline" size="sm" onClick={onBackToFindings}>
            Back to Findings
          </Button>
        }
      />

      {/* Side-by-side Requirement Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <RequirementCard
          id={finding.reqA.id}
          title={finding.reqA.title}
          body={finding.reqA.body}
          version={finding.reqA.version}
          category={finding.reqA.category}
          section={finding.reqA.section}
          owner={finding.reqA.owner}
          accentColor="amber"
        />

        <RequirementCard
          id={finding.reqB.id}
          title={finding.reqB.title}
          body={finding.reqB.body}
          version={finding.reqB.version}
          category={finding.reqB.category}
          section={finding.reqB.section}
          owner={finding.reqB.owner}
          accentColor="amber"
        />
      </div>

      {/* Details & Actions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): AI Explanation + Reviewer Notes */}
        <div className="lg:col-span-2 space-y-5">
          <AIExplanationCard
            severity={finding.severity}
            confidence={finding.confidence}
            explanation={finding.explanation}
            recommendation={finding.recommendation}
          />

          {/* Reviewer Notes Card */}
          <Card>
            <div className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-900 text-sm">
                  Reviewer notes
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  Draft · Not submitted
                </span>
              </div>

              <Textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Record your assessment, reasoning, or findings..."
                helperText="Notes are recorded with your decision. Accept and Dismiss require a rationale."
              />

              <div className="pt-2 text-xs text-slate-500 font-normal border-t border-slate-100 flex items-center justify-between">
                <span>
                  Reviewer: <strong className="text-slate-700">Abhijeet</strong> ·{" "}
                  {currentStatus === "Pending Review"
                    ? "No review decision has been recorded."
                    : `Decision recorded: ${currentStatus}`}
                </span>
              </div>
            </div>
          </Card>
        </div>

        {/* Right Column (1 span): Review Actions */}
        <div className="space-y-4">
          <Card>
            <CardContent className="p-5 space-y-5">
              <div>
                <h3 className="font-semibold text-slate-900 text-base mb-1">
                  Choose a review action
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Your decision owns the outcome. AI confidence alone does not confirm a conflict.
                </p>
              </div>

              {/* Accept & Dismiss Buttons */}
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-2.5">
                  <Button
                    variant="outline"
                    size="md"
                    onClick={() => handleAction("accept")}
                    leftIcon={<CheckIcon size={16} className="text-emerald-600" />}
                    className="hover:border-emerald-500 hover:bg-emerald-50/30 font-medium"
                  >
                    Accept
                  </Button>
                  <Button
                    variant="outline"
                    size="md"
                    onClick={() => handleAction("dismiss")}
                    leftIcon={<XIcon size={16} className="text-rose-600" />}
                    className="hover:border-rose-500 hover:bg-rose-50/30 font-medium"
                  >
                    Dismiss
                  </Button>
                </div>
                <p className="text-[11px] text-slate-400 leading-tight">
                  Accept: confirm a conflict that still needs a fix. Dismiss: record why this is not a conflict.
                </p>
              </div>

              <div className="border-t border-slate-100 pt-4 space-y-2">
                <Button
                  variant="outline"
                  size="md"
                  onClick={() => handleAction("resolve")}
                  className="w-full justify-center text-slate-800"
                >
                  Resolve Conflict
                </Button>
                <p className="text-[11px] text-slate-400 leading-tight">
                  Document an agreed requirement change and rationale. Only then mark the finding Resolved.
                </p>
              </div>

              <div className="border-t border-slate-100 pt-4 space-y-2">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => onRequestClarification(finding.id)}
                  leftIcon={<MessageSquareIcon size={16} />}
                  className="w-full justify-center bg-blue-600 hover:bg-blue-700"
                >
                  Request Clarification
                </Button>
                <p className="text-[11px] text-slate-400 leading-tight">
                  Open the question draft for the owners. Opening a draft does not change the finding status.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Sub-footer metadata */}
      <div className="text-xs text-slate-400 border-t border-slate-200/60 pt-4 flex flex-col sm:flex-row justify-between gap-2">
        <span>
          {finding.id} · Detected {finding.detectedAt} · Source text preserved from baseline {finding.baseline}
        </span>
        <span>Requirements baseline {finding.baseline}</span>
      </div>

      {/* Action Confirmation Dialog */}
      <ConfirmDialog
        isOpen={confirmAction !== null}
        onClose={() => setConfirmAction(null)}
        onConfirm={executeAction}
        title={
          confirmAction === "accept"
            ? "Confirm Requirement Conflict?"
            : confirmAction === "dismiss"
            ? "Dismiss Finding?"
            : "Mark Finding as Resolved?"
        }
        description={
          confirmAction === "accept"
            ? "Confirming this conflict records that a conflict exists between the requirements and queues it for change management."
            : confirmAction === "dismiss"
            ? "Dismissing this finding marks it as a non-conflict or expected behavior. Rationale will be recorded in the audit trail."
            : "Resolving requires that a mutual agreement on requirement changes has been reached by the owners."
        }
        variant={confirmAction === "dismiss" ? "warning" : "primary"}
        confirmLabel={
          confirmAction === "accept"
            ? "Accept Conflict"
            : confirmAction === "dismiss"
            ? "Dismiss Finding"
            : "Confirm Resolved"
        }
      />
    </div>
  );
}
