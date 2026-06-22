import { useState, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import { getLastUsedMember, setLastUsedMember } from "@/lib/member-context";

interface MemberItem {
  id: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
}

interface MemberPickerProps {
  members: MemberItem[];
  value: string;
  onChange: (id: string) => void;
  persistLastUsed?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function MemberPicker({
  members,
  value,
  onChange,
  persistLastUsed = true,
  size = "sm",
  className,
}: MemberPickerProps) {
  const [open, setOpen] = useState(false);

  const activeMembers = members.filter((m) => m.is_active);
  const selected = activeMembers.find((m) => m.id === value);

  // Auto-select last-used member on mount if no value
  useEffect(() => {
    if (value) return;
    const last = getLastUsedMember();
    if (last && activeMembers.some((m) => m.id === last.id)) {
      onChange(last.id);
    } else if (activeMembers.length > 0) {
      onChange(activeMembers[0].id);
    }
  }, [value, activeMembers, onChange]);

  function handleSelect(id: string) {
    onChange(id);
    setOpen(false);
    if (persistLastUsed) {
      const member = activeMembers.find((m) => m.id === id);
      if (member) setLastUsedMember(id, `${member.first_name} ${member.last_name}`);
    }
  }

  if (size === "md") {
    return (
      <div className={`relative ${className ?? ""}`}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex items-center justify-between w-full rounded-lg border px-3 py-2 text-sm bg-background hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-semibold">
              {selected?.first_name?.[0] || "?"}
            </div>
            <span className="font-medium text-xs">
              {selected ? `${selected.first_name} ${selected.last_name}` : "Select member"}
            </span>
          </div>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
        {open && (
          <div className="absolute top-full left-0 right-0 mt-1 rounded-lg border bg-popover shadow-lg z-30 max-h-40 overflow-y-auto">
            {activeMembers.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => handleSelect(m.id)}
                className={`flex items-center w-full px-3 py-2 text-xs hover:bg-muted transition-colors ${
                  m.id === value ? "bg-primary/5 font-semibold" : ""
                }`}
              >
                {m.first_name} {m.last_name}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // sm size — compact tag style
  return (
    <div className={`relative ${className ?? ""}`}>
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-[10px] font-semibold bg-secondary hover:bg-muted text-foreground px-2 py-0.5 rounded transition-colors border"
      >
        <span>For: {selected ? selected.first_name : "Select"}</span>
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-36 rounded-md border bg-popover shadow-lg z-20 max-h-40 overflow-y-auto">
          {activeMembers.map((m) => (
            <button
              key={m.id}
              onClick={() => handleSelect(m.id)}
              className={`flex items-center w-full px-2 py-1.5 text-[10px] text-left hover:bg-muted transition-colors ${
                m.id === value ? "bg-primary/5 font-semibold text-primary" : ""
              }`}
            >
              {m.first_name} {m.last_name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
