import { useParams, useNavigate, useLocation } from "react-router-dom";
import { BatchUploadQueue } from "@/components/records/batch-upload-queue";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import { FolderOpen } from "lucide-react";

export default function BatchRecordPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const initialFiles = (location.state as { files?: File[] } | null)?.files;

  if (!memberId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to={`/members/${memberId}/records`} className="hover:underline">
          Records
        </Link>
        <span>/</span>
        <h1 className="text-2xl font-bold text-foreground">Batch Upload</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-blue-500" />
            Upload Multiple Records
          </CardTitle>
        </CardHeader>
        <CardContent>
          <BatchUploadQueue
            memberId={memberId}
            initialFiles={initialFiles}
            onComplete={() => navigate(`/members/${memberId}/records`)}
          />
        </CardContent>
      </Card>
    </div>
  );
}
