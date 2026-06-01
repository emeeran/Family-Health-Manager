import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Stethoscope, Phone, MapPin, Clock, Trash2, User } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { deleteProvider } from "@/lib/api/providers";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { formatDate } from "@/lib/utils";
import type { ProviderResponse } from "@/lib/types/provider";

const SPECIALTY_COLORS: Record<string, string> = {
  cardiology: "from-red-500 to-rose-500",
  dermatology: "from-amber-500 to-orange-500",
  "general practice": "from-emerald-500 to-teal-500",
  neurology: "from-violet-500 to-purple-500",
  oncology: "from-pink-500 to-rose-500",
  orthopedics: "from-blue-500 to-cyan-500",
  pediatrics: "from-green-500 to-emerald-500",
  psychiatry: "from-indigo-500 to-violet-500",
  default: "from-violet-500 to-blue-500",
};

function ProviderAvatar({ name, speciality }: { name: string; speciality?: string | null }) {
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const gradient = SPECIALTY_COLORS[(speciality || "").toLowerCase()] || SPECIALTY_COLORS.default;

  return (
    <div
      className={`flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br ${gradient} text-white text-sm font-bold shadow-sm`}
    >
      {initials}
    </div>
  );
}

interface ProvidersContentProps {
  providers: ProviderResponse[];
}

export function ProvidersContent({ providers }: ProvidersContentProps) {
  const { mutate } = useSWRConfig();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");

  async function handleDelete() {
    try {
      await deleteProvider(deleteId);
      toast.success("Provider deleted");
      setDeleteOpen(false);
      await Promise.all([mutate("providers"), mutate("dashboard")]);
    } catch {
      toast.error("Failed to delete provider");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Healthcare Providers</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {providers.length} provider{providers.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link to="/providers/new">
          <Button className="shadow-sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Add Provider
          </Button>
        </Link>
      </div>

      {providers.length === 0 ? (
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10">
              <Stethoscope className="h-8 w-8 text-emerald-500" />
            </div>
          }
          title="No providers yet"
          description="Add a healthcare provider to start managing their assignments."
          action={
            <Link to="/providers/new">
              <Button className="shadow-sm">Add First Provider</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {providers.map((provider) => (
            <Card
              key={provider.id}
              className="group hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 overflow-hidden"
            >
              <CardHeader className="pb-2">
                <div className="flex items-center gap-3">
                  <ProviderAvatar name={provider.name} speciality={provider.speciality} />
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-base">
                      <Link
                        to={`/providers/${provider.id}`}
                        className="hover:text-primary transition-colors"
                      >
                        {provider.name}
                      </Link>
                    </CardTitle>
                    {provider.speciality && (
                      <p className="text-xs text-muted-foreground mt-0.5">{provider.speciality}</p>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 pt-0">
                {(provider.assigned_members?.length ?? 0) > 0 && (
                  <div className="space-y-1">
                    {provider.assigned_members.map((m) => (
                      <Link
                        key={m.family_member_id}
                        to={`/people/${m.family_member_id}`}
                        className="flex items-center justify-between text-xs rounded px-1.5 py-1 hover:bg-muted/50 transition-colors"
                      >
                        <span className="flex items-center gap-1.5 min-w-0">
                          <User className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                          <span className="truncate font-medium">{m.family_member_name}</span>
                          {m.visit_count > 0 && (
                            <span className="text-muted-foreground shrink-0">
                              {m.visit_count} visit{m.visit_count !== 1 ? "s" : ""}
                            </span>
                          )}
                        </span>
                        {m.uhid && (
                          <span className="font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded text-xs ml-2 shrink-0">
                            {m.uhid}
                          </span>
                        )}
                      </Link>
                    ))}
                  </div>
                )}
                {provider.phone && (
                  <p className="text-sm text-muted-foreground flex items-center gap-2">
                    <Phone className="h-3.5 w-3.5 text-muted-foreground/60" />
                    {provider.phone}
                  </p>
                )}
                {provider.address && (
                  <p className="text-sm text-muted-foreground flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5 text-muted-foreground/60" />
                    <span className="line-clamp-1">{provider.address}</span>
                  </p>
                )}
                <div className="flex items-center justify-between pt-1">
                  <p className="text-xs text-muted-foreground/60 flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Added {formatDate(provider.created_at)}
                  </p>
                  <button
                    onClick={() => {
                      setDeleteId(provider.id);
                      setDeleteOpen(true);
                    }}
                    className="text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100 p-1"
                    aria-label={`Delete ${provider.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Provider"
        description="Are you sure you want to delete this provider? Their assignments will also be removed."
        onConfirm={handleDelete}
      />
    </div>
  );
}
