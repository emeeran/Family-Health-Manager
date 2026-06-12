import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
  /** Layout variant controlling padding and icon size */
  variant?: "default" | "compact" | "illustrated";
  /** Optional illustration to render instead of icon (used with "illustrated" variant) */
  illustration?: React.ReactNode;
}

const variantStyles: Record<string, string> = {
  default: "py-16",
  compact: "py-8",
  illustrated: "py-20",
};

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  variant = "default",
  illustration,
}: EmptyStateProps) {
  const visual = illustration || icon;
  const isIllustrated = variant === "illustrated" && illustration;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center animate-fade-in-up",
        variantStyles[variant],
        className
      )}
    >
      {visual && (
        <div className={cn(isIllustrated ? "mb-6" : "mb-4", isIllustrated && "opacity-80")}>
          {visual}
        </div>
      )}
      <h3 className="text-lg font-semibold">{title}</h3>
      {description && (
        <p className="mt-1.5 text-sm text-muted-foreground max-w-sm">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
