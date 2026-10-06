import React from "react";
import { Loader2 } from "lucide-react";

const variants = {
  primary: "bg-accent hover:bg-accent-hover text-accent-foreground shadow-sm border border-accent/40 active:opacity-90",
  secondary: "bg-bg-surface hover:bg-bg-surface-elevated text-text-main border border-border-subtle hover:border-border-muted shadow-xs",
  ghost: "bg-transparent hover:bg-bg-surface text-text-muted hover:text-text-main",
  danger: "bg-status-danger-bg text-status-danger border border-status-danger-border hover:opacity-90",
};

const sizes = {
  sm: "px-3 py-1.5 min-h-[44px] text-xs font-medium rounded-lg gap-1.5",
  md: "px-4 py-2 min-h-[44px] text-xs font-semibold rounded-md gap-2",
  lg: "px-5 py-2.5 min-h-[44px] text-sm font-semibold rounded-md gap-2",
  icon: "p-2 min-h-[44px] min-w-[44px] rounded-md text-text-muted hover:text-text-main hover:bg-bg-surface-elevated",
};

export default function Button({
  children,
  variant = "secondary",
  size = "md",
  loading = false,
  disabled = false,
  className = "",
  type = "button",
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-2 ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      {children}
    </button>
  );
}
