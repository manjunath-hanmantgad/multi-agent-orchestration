import { cn } from "@/lib/utils";
import { cva } from "class-variance-authority";

const statusBadgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      status: {
        APPROVED: "border-transparent text-white bg-[#16a34a] hover:bg-[#15803d]",
        REJECTED: "border-transparent text-white bg-[#dc2626] hover:bg-[#b91c1c]",
        PAUSED: "border-transparent text-white bg-[#d97706] hover:bg-[#b45309]",
        RUNNING: "border-transparent text-white bg-[#2563eb] hover:bg-[#1d4ed8]",
        PENDING: "border-transparent text-white bg-[#6b7280] hover:bg-[#4b5563]",
        COMPLETED: "border-transparent text-white bg-[#16a34a] hover:bg-[#15803d]",
        FAILED: "border-transparent text-white bg-[#dc2626] hover:bg-[#b91c1c]",
      },
    },
    defaultVariants: {
      status: "PENDING",
    },
  }
);

const STATUS_KEYS = new Set([
  "APPROVED", "REJECTED", "PAUSED", "RUNNING",
  "PENDING", "COMPLETED", "FAILED",
] as const);

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  status: string;
}

export function StatusBadge({ status, className, ...props }: StatusBadgeProps) {
  const normalized = status.toUpperCase();
  const variant = STATUS_KEYS.has(normalized as never) ? normalized : "PENDING";
  return (
    <span className={cn(statusBadgeVariants({ status: variant as any }), className)} {...props}>
      {status}
    </span>
  );
}
