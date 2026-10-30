import React, { useState } from "react";
import {
  PageHeader,
  Card,
  CardContent,
  Button,
  ProgressBar,
  UploadCloudIcon,
  FileTextIcon,
  CheckIcon,
  useToast,
} from "../components/ui";

export function UploadPage() {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isExtracted, setIsExtracted] = useState(false);

  const handleSimulatedUpload = () => {
    if (!file) {
      toast.error("Please choose or drop an SRS document first.", "No file selected");
      return;
    }
    setIsUploading(true);
    setUploadProgress(20);

    const timer1 = setTimeout(() => setUploadProgress(60), 400);
    const timer2 = setTimeout(() => {
      setUploadProgress(100);
      setIsUploading(false);
      setIsExtracted(true);
      toast.success("Document uploaded and 12 requirements extracted.", "Extraction Complete");
    }, 900);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  };

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[{ label: "Atlas Customer Portal" }, { label: "Upload SRS" }]}
        title="Upload SRS Document"
        description="Upload a software requirements specification (PDF or DOCX). The extraction pipeline automatically segments and numbers requirements."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardContent className="p-8">
              <div
                className="border-2 border-dashed border-slate-300 rounded-2xl p-8 flex flex-col items-center justify-center text-center hover:border-blue-400 transition-colors bg-slate-50/50 cursor-pointer"
                onClick={() => {
                  // Simulate file selection
                  const dummy = new File(["dummy SRS content"], "Atlas_Customer_Portal_SRS_v1.4.pdf", {
                    type: "application/pdf",
                  });
                  setFile(dummy);
                  setIsExtracted(false);
                }}
              >
                <div className="w-14 h-14 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                  <UploadCloudIcon size={28} />
                </div>
                <h3 className="text-base font-semibold text-slate-900 mb-1">
                  Click to select or drag and drop your SRS document
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mb-4">
                  Supports PDF and DOCX files up to 25MB. Text extraction adheres to ADR-28 segmentation guidelines.
                </p>

                {file && (
                  <div className="mt-2 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200">
                    <FileTextIcon size={14} />
                    <span>{file.name} (1.4 MB)</span>
                  </div>
                )}
              </div>

              {isUploading && (
                <div className="mt-6 space-y-2">
                  <ProgressBar
                    value={uploadProgress}
                    showValue
                    label="Extracting requirements and segmenting clauses..."
                  />
                </div>
              )}

              {isExtracted && (
                <div className="mt-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-3">
                  <CheckIcon size={18} className="text-emerald-600 shrink-0" />
                  <div>
                    <span className="font-semibold block text-emerald-900">
                      Extraction complete: 12 requirements identified
                    </span>
                    <span>
                      Clauses mapped to security, session, network, and reporting modules.
                    </span>
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-end gap-3">
                <Button
                  variant="outline"
                  size="md"
                  onClick={() => {
                    setFile(null);
                    setIsExtracted(false);
                  }}
                  disabled={isUploading || !file}
                >
                  Clear
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  onClick={handleSimulatedUpload}
                  isLoading={isUploading}
                  disabled={!file || isExtracted}
                >
                  Process & Extract
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="p-5 space-y-3">
              <h4 className="text-sm font-semibold text-slate-900">
                Sprint 1 Scope (US-01 / US-02)
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                Ingestion parses uploaded SRS documents and extracts requirement blocks with their structural hierarchy and source IDs.
              </p>
              <div className="pt-2 border-t border-slate-100 text-xs text-slate-500 space-y-1">
                <div>• Ingestion owner: <strong>Bansil</strong></div>
                <div>• Upload UI owner: <strong>Pranshu</strong></div>
                <div>• UI Foundation: <strong>Abhijeet</strong></div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
