import { useSearchParams, useNavigate } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { BatchUploadQueue } from "@/components/records/batch-upload-queue";
import { Card, CardContent } from "@/components/ui/card";
import { FileUp } from "lucide-react";

export default function AiToolsDocumentExtractionPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const navigate = useNavigate();

  return (
    <AiToolsSubPage title="Document Extraction">
      <Card>
        <CardContent className="flex items-start gap-3 py-4">
          <div className="h-8 w-8 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0">
            <FileUp className="h-4 w-4 text-indigo-500" />
          </div>
          <div>
            <p className="text-sm font-medium">Upload medical documents</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Drop PDFs or images and AI will extract diagnoses, prescriptions, lab results, and
              other structured data — then create health records automatically.
            </p>
          </div>
        </CardContent>
      </Card>

      <BatchUploadQueue
        memberId={memberId}
        onComplete={() => navigate(`/people/${memberId}/records`)}
      />
    </AiToolsSubPage>
  );
}
