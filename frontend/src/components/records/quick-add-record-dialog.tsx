import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useSWRConfig } from "swr";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Stethoscope, FlaskConical, Eye, Heart, FileText, Activity, Brain } from "lucide-react";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { QuickBloodGlucoseForm } from "./quick-blood-glucose-form";
import { QuickVitalsForm } from "./quick-vitals-form";
import { QuickParkinsonsForm } from "./quick-parkinsons-form";

interface QuickAddRecordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  members: FamilyMemberResponse[];
}

type Step = "select-member" | "select-type" | "form";

const RECORD_TYPE_ICONS: Record<RecordType, React.ReactNode> = {
  doctor_visit: <Stethoscope className="h-5 w-5" />,
  lab_report: <FlaskConical className="h-5 w-5" />,
  rx_eyeglass: <Eye className="h-5 w-5" />,
  blood_glucose: <Heart className="h-5 w-5" />,
  hba1c: <Heart className="h-5 w-5" />,
  misc_record: <FileText className="h-5 w-5" />,
  vitals: <Activity className="h-5 w-5" />,
  parkinsons_log: <Brain className="h-5 w-5" />,
};

const RECORD_TYPE_COLORS: Record<RecordType, string> = {
  doctor_visit: "bg-teal-500/10 text-teal-600",
  lab_report: "bg-emerald-500/10 text-emerald-600",
  rx_eyeglass: "bg-purple-500/10 text-purple-600",
  blood_glucose: "bg-rose-500/10 text-rose-600",
  hba1c: "bg-rose-500/10 text-rose-600",
  misc_record: "bg-slate-500/10 text-slate-600",
  vitals: "bg-blue-500/10 text-blue-600",
  parkinsons_log: "bg-indigo-500/10 text-indigo-600",
};

/** Types that have inline quick forms */
const QUICK_FORM_TYPES: RecordType[] = ["blood_glucose", "vitals", "parkinsons_log"];

export function QuickAddRecordDialog({ open, onOpenChange, members }: QuickAddRecordDialogProps) {
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();
  const [step, setStep] = useState<Step>("select-member");
  const [selectedMember, setSelectedMember] = useState<FamilyMemberResponse | null>(null);
  const [selectedType, setSelectedType] = useState<RecordType | null>(null);

  const reset = useCallback(() => {
    setStep("select-member");
    setSelectedMember(null);
    setSelectedType(null);
  }, []);

  const handleClose = useCallback(
    (value: boolean) => {
      onOpenChange(value);
      if (!value) reset();
    },
    [onOpenChange, reset]
  );

  const handleSelectMember = useCallback((member: FamilyMemberResponse) => {
    setSelectedMember(member);
    setStep("select-type");
  }, []);

  const handleSelectType = useCallback(
    (type: RecordType) => {
      if (QUICK_FORM_TYPES.includes(type)) {
        setSelectedType(type);
        setStep("form");
      } else {
        // Navigate to full form for complex types
        handleClose(false);
        navigate(`/people/${selectedMember!.id}/records/new?type=${type}`);
      }
    },
    [selectedMember, handleClose, navigate]
  );

  const handleQuickFormSuccess = useCallback(() => {
    handleClose(false);
    if (selectedMember) {
      Promise.all([mutate("dashboard"), mutate(`member-detail-${selectedMember.id}`)]);
    } else {
      mutate("dashboard");
    }
  }, [handleClose, mutate, selectedMember]);

  const handleBack = useCallback(() => {
    if (step === "form") {
      setStep("select-type");
      setSelectedType(null);
    } else if (step === "select-type") {
      setStep("select-member");
      setSelectedMember(null);
    }
  }, [step]);

  const activeMembers = members.filter((m) => m.is_active);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md p-0 gap-0 overflow-hidden">
        <DialogTitle className="sr-only">Quick Add Record</DialogTitle>
        <DialogDescription className="sr-only">
          Quickly create a new health record
        </DialogDescription>

        {/* Header */}
        <div className="flex items-center gap-3 border-b px-4 py-3">
          {step !== "select-member" && (
            <button
              onClick={handleBack}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Back
            </button>
          )}
          <h2 className="text-sm font-semibold">
            {step === "select-member" && "Who is this record for?"}
            {step === "select-type" && `Record for ${selectedMember?.first_name}`}
            {step === "form" && `${RECORD_TYPE_LABELS[selectedType!]}`}
          </h2>
        </div>

        {/* Content */}
        <div className="p-4">
          {step === "select-member" && (
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {activeMembers.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No active members. Add a member first.
                </p>
              ) : (
                activeMembers.map((member) => {
                  const initials = `${member.first_name[0]}${member.last_name[0]}`.toUpperCase();
                  return (
                    <button
                      key={member.id}
                      onClick={() => handleSelectMember(member)}
                      className="flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-sm hover:bg-muted/50 transition-colors text-left"
                    >
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300 text-xs font-bold">
                        {initials}
                      </div>
                      <div>
                        <p className="font-medium">
                          {member.first_name} {member.last_name}
                        </p>
                        <p className="text-xs text-muted-foreground">{member.relationship}</p>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          )}

          {step === "select-type" && (
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(RECORD_TYPE_LABELS) as RecordType[])
                .filter((t) => t !== "hba1c")
                .map((type) => (
                  <button
                    key={type}
                    onClick={() => handleSelectType(type)}
                    className="flex flex-col items-center gap-2 rounded-lg border p-3 hover:bg-muted/50 transition-colors"
                  >
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-lg ${RECORD_TYPE_COLORS[type]}`}
                    >
                      {RECORD_TYPE_ICONS[type]}
                    </div>
                    <span className="text-xs font-medium text-center">
                      {RECORD_TYPE_LABELS[type]}
                    </span>
                  </button>
                ))}
            </div>
          )}

          {step === "form" && selectedMember && selectedType && (
            <>
              {selectedType === "blood_glucose" && (
                <QuickBloodGlucoseForm
                  memberId={selectedMember.id}
                  onSuccess={handleQuickFormSuccess}
                  onCancel={handleBack}
                />
              )}
              {selectedType === "vitals" && (
                <QuickVitalsForm
                  memberId={selectedMember.id}
                  onSuccess={handleQuickFormSuccess}
                  onCancel={handleBack}
                />
              )}
              {selectedType === "parkinsons_log" && (
                <QuickParkinsonsForm
                  memberId={selectedMember.id}
                  onSuccess={handleQuickFormSuccess}
                  onCancel={handleBack}
                />
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
