import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-on-primary border-2 border-primary hover:brightness-110",
  secondary: "bg-transparent text-text border-2 border-line hover:border-accent",
  danger: "bg-danger-bg text-on-danger border-2 border-danger-bg hover:brightness-110",
  ghost: "bg-transparent text-text border-2 border-transparent hover:border-line",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  icon?: ReactNode;
  size?: "sm" | "md";
}

/** Buttons use Courier New bold (index.css). A ghost button with only an icon needs aria-label. */
export function Button({
  variant = "secondary",
  busy = false,
  icon,
  size = "md",
  children,
  disabled,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const pad = size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm";
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex items-center justify-center gap-1.5 rounded-sm ${pad} transition-[filter,border-color] duration-200 ease-out disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}
