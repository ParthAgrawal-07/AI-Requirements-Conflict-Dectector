import React, { useState } from "react";
import {
  PageHeader,
  StatusBadge,
  SeverityBadge,
  ConfidenceBadge,
  RequirementBadge,
  Button,
  Textarea,
  Card,
  CardContent,
  useToast,
} from "../components/ui";
import { sampleFindings, FindingDetail } from "../lib/sampleData";

export interface ClarificationPageProps {
  findingId: string;
  onBackToReview: (id: string) => void;
  onBackToFindings: () => void;
}

export function ClarificationPage({
  findingId,
  onBackToReview,
  onBackToFindings,
}: ClarificationPageProps) {
  const toast = useToast();
  const finding: FindingDetail =
    sampleFindings.find((f) => f.id === findingId) || sampleFindings[0];

  const clarification = finding.clarification || {
    question: "Clarification question for this finding",
    answerDraft: "",
    owners: ["Priya Shah", "Daniel Kim"],
    history: [],
    stillOpen: "",
  };

  const [answer, setAnswer] = useState(clarification.answerDraft);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDraftSaved, setIsDraftSaved] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim()) {
      toast.error("Please enter an answer before submitting.", "Submission Failed");
      return;
    }

    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      toast.success(
        "Clarification response submitted. F-001 remains in Pending Review.",
        "Clarification Submitted"
      );
      onBackToReview(finding.id);
    }, 600);
  };

  const handleSaveDraft = () => {
    setIsDraftSaved(true);
    toast.info("Draft response saved privately.", "Draft Saved");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Findings", onClick: onBackToFindings },
          { label: finding.id, onClick: () => onBackToReview(finding.id) },
          { label: "Review", onClick: () => onBackToReview(finding.id) },
          { label: "Clarification" },
        ]}
        title="Clarify session behavior"
        badge={<StatusBadge status={finding.status} />}
        description="Capture the requirement owners' answer. Clarification provides evidence for review; it does not resolve the finding."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => onBackToReview(finding.id)}
          >
            Back to Review
          </Button>
        }
      />

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Question & Answer */}
        <div className="lg:col-span-7 space-y-5">
          <Card>
            <CardContent className="p-6 space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-base font-semibold text-slate-900">
                  Question & answer
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  {isDraftSaved ? "Draft saved" : "Draft · Not submitted"}
                </span>
              </div>

              {/* AI Question Box */}
              <div className="space-y-2 bg-blue-50/50 border border-blue-100 p-4 rounded-xl">
                <span className="text-[11px] font-bold uppercase tracking-wider text-blue-700 block">
                  AI-Generated Question · Editorial Review Required
                </span>
                <p className="text-sm font-semibold text-slate-900 leading-relaxed">
                  {clarification.question}
                </p>
              </div>

              {/* Answer Input */}
              <div className="space-y-2">
                <Textarea
                  label="Answer from requirement owners"
                  rows={4}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Enter the agreed session definition, expected idle-user behavior, and any explicit exception. Cite the owner or source supporting the answer."
                  helperText="An answer is required to submit. If the policy is still undecided, save a draft instead."
                />
              </div>

              {/* Requirement Owners Row */}
              <div className="flex items-center gap-2 text-xs text-slate-500 pt-1">
                <span className="font-semibold text-slate-700">Requirement owners:</span>
                <span>{clarification.owners.join(" · ")}</span>
              </div>

              {/* After you submit Callout */}
              <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4 space-y-1">
                <h4 className="text-xs font-semibold text-slate-900">After you submit</h4>
                <p className="text-xs text-slate-600 leading-relaxed">
                  A &ldquo;Clarification submitted&rdquo; confirmation will appear and the answer will be added to this thread. {finding.id} stays Pending Review until a reviewer records a decision.
                </p>
              </div>

              {/* Action Buttons */}
              <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                <Button
                  variant="primary"
                  size="md"
                  onClick={handleSubmit}
                  isLoading={isSubmitting}
                  className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700"
                >
                  Submit Clarification
                </Button>
                <Button
                  variant="outline"
                  size="md"
                  onClick={handleSaveDraft}
                  className="w-full sm:w-auto"
                >
                  Save Draft
                </Button>
              </div>

              <p className="text-[11px] text-slate-400">
                Save Draft keeps your work without notifying owners or changing the finding status.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Right Column (5 cols): Affected Requirements & Previous Exchanges */}
        <div className="lg:col-span-5 space-y-5">
          {/* Affected Requirements Card */}
          <Card>
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-900">
                  Affected requirements
                </h3>
                <span className="text-xs font-mono font-medium text-slate-400">
                  {finding.id}
                </span>
              </div>

              <div className="space-y-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5">
                    <RequirementBadge reqId={finding.reqA.id} />
                    <span className="text-xs font-semibold text-slate-800">
                      {finding.reqA.title}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed pl-1">
                    {finding.reqA.body}
                  </p>
                </div>

                <div className="space-y-1 pt-2 border-t border-slate-100">
                  <div className="flex items-center gap-1.5">
                    <RequirementBadge reqId={finding.reqB.id} />
                    <span className="text-xs font-semibold text-slate-800">
                      {finding.reqB.title}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed pl-1">
                    {finding.reqB.body}
                  </p>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center gap-2 flex-wrap text-xs">
                <SeverityBadge severity={finding.severity} />
                <ConfidenceBadge confidence={finding.confidence} />
                <span className="text-slate-400">·</span>
                <span className="text-slate-600 font-medium">Possible conflict</span>
              </div>
            </CardContent>
          </Card>

          {/* Previous Exchanges Card */}
          <Card>
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-900">
                  Previous exchanges
                </h3>
                <span className="text-xs text-slate-400">12 Oct 2026</span>
              </div>

              <div className="space-y-4">
                {clarification.history.map((item, idx) => (
                  <div key={idx} className="space-y-1 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-900">
                        {item.author} <span className="font-normal text-slate-400">· {item.role}</span>
                      </span>
                      <span className="font-mono text-slate-400">{item.time}</span>
                    </div>
                    <p className="text-slate-600 leading-relaxed bg-slate-50/70 p-2.5 rounded-lg border border-slate-100">
                      {item.text}
                    </p>
                  </div>
                ))}
              </div>

              {clarification.stillOpen && (
                <div className="pt-2 border-t border-slate-100">
                  <p className="text-xs font-semibold text-amber-800 bg-amber-50 p-2.5 rounded-lg border border-amber-200/80">
                    Still open: {clarification.stillOpen}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Sub-footer metadata */}
      <div className="text-xs text-slate-400 border-t border-slate-200/60 pt-4 flex flex-col sm:flex-row justify-between gap-2">
        <span>
          {finding.id} · Clarification draft · {answer ? "Answer drafted" : "No answer or review decision submitted"}
        </span>
        <span>Requirements baseline {finding.baseline}</span>
      </div>
    </div>
  );
}
