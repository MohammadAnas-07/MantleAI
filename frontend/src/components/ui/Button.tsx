import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "border-primary bg-primary text-on-primary hover:bg-primary-hover",
  secondary: "border-field bg-paper text-text hover:border-text hover:bg-hover",
  danger: "border-danger bg-danger text-on-danger hover:opacity-90",
  ghost: "border-transparent bg-transparent text-text hover:bg-hover",
};

const SIZES = {
  sm: "h-7 gap-1 px-2 text-sm",
  md: "h-8 gap-1.5 px-3 text-base",
} as const;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  icon?: ReactNode;
  size?: keyof typeof SIZES;
}

/**
 * One primary button per view; the rest are secondary or ghost (docs/design-app.md). A ghost
 * button with only an icon needs an aria-label.
 */
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
  // An icon-only button is square, so its hit area doesn't shrink to the icon.
  const iconOnly = !children && Boolean(icon || busy);
  const shape = iconOnly
    ? size === "sm"
      ? "size-7 justify-center"
      : "size-8 justify-center"
    : SIZES[size];
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex shrink-0 items-center justify-center rounded-sm border font-medium whitespace-nowrap transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50 ${shape} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}
