import { useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Phone, MapPin, Users } from "lucide-react";
import { deleteProvider } from "@/lib/api/providers";
import { formatDate } from "@/lib/utils";
import { toast } from "sonner";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ProviderAssignmentResponse } from "@/lib/types/provider-assignment";

interface ProviderDetailContentProps {
  provider: ProviderResponse;
  assignedMembers: ProviderAssignmentResponse[];
}

export function ProviderDetailContent({ provider, assignedMembers }: ProviderDetailContentProps) {
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);

  async function handleDelete() {
    try {
      await deleteProvider(provider.id);
      toast.success("Provider deleted");
      navigate("/providers");
    } catch {
      toast.error("Failed to delete provider");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/providers" className="hover:underline">
          Providers
        </Link>
        <span>/</span>
        <span className="text-foreground">{provider.name}</span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{provider.name}</h1>
        <div className="flex gap-2">
          <Link to={`/providers/${provider.id}/edit`}>
            <Button variant="outline">Edit</Button>
          </Link>
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Provider Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {provider.speciality && (
            <>
              <div>
                <span className="text-muted-foreground">Speciality:</span> {provider.speciality}
              </div>
              <Separator />
            </>
          )}
          {provider.phone && (
            <>
              <div className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-muted-foreground" />
                <span>{provider.phone}</span>
              </div>
              <Separator />
            </>
          )}
          {provider.address && (
            <>
              <div className="flex items-start gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                <span className="whitespace-pre-wrap">{provider.address}</span>
              </div>
              <Separator />
            </>
          )}
          <div>
            <span className="text-muted-foreground">Added:</span> {formatDate(provider.created_at)}
          </div>
        </CardContent>
      </Card>

      {/* Assigned Members */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Users className="h-4 w-4" />
            Assigned Members ({assignedMembers.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {assignedMembers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No family members assigned to this provider yet.
            </p>
          ) : (
            <div className="divide-y">
              {assignedMembers.map((a) => (
                <Link
                  key={a.id}
                  to={`/people/${a.family_member_id}`}
                  className="flex items-center justify-between py-2.5 first:pt-0 last:pb-0 hover:bg-muted/30 -mx-2 px-2 rounded transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{a.family_member_name}</p>
                    <p className="text-xs text-muted-foreground">Member</p>
                  </div>
                  {a.uhid && (
                    <div className="text-right shrink-0 ml-4">
                      <p className="text-xs font-mono bg-muted px-2 py-0.5 rounded">{a.uhid}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">UHID</p>
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Provider"
        description="Are you sure you want to delete this provider? This will not affect existing records."
        onConfirm={handleDelete}
      />
    </div>
  );
}
