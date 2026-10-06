import React from "react";
import { Loader2 } from "lucide-react";

const variants = {
  primary: "bg-accent hover:bg-accent-hover text-white shadow-md border border-accent/40 active:opacity-90",
  secondary: "bg-bg-surface hover:bg-bg-surface-elevated text-text-main border border-border-subtle hover:border-border-muted shadow-sm",
  ghost: "bg-transparent hover:bg-bg-surface text-text-muted hover:text-text-main",
  danger: "bg-status-danger-bg text-status-danger border border-status-danger-border hover:opacity-90",
};

const sizes = {
  sm: "px-2.5 py-1.5 text-xs rounded-lg gap-1.5",
  md: "px-3.5 py-2 text-xs font-semibold rounded-xl gap-2",
  lg: "px-5 py-2.5 text-sm font-semibold rounded-xl gap-2",
  icon: "p-2 rounded-xl text-text-muted hover:text-text-main hover:bg-bg-surface-elevated",
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
      className={`inline-flex items-center justify-center font-medium transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed select-none ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      {children}
    </button>
  );
}
