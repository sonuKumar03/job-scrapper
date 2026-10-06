import React from "react";

const variants = {
  default: "bg-bg-surface-elevated text-text-muted border-border-subtle",
  success: "bg-status-success-bg text-status-success border-status-success-border",
  running: "bg-status-running-bg text-status-running border-status-running-border animate-pulse",
  warning: "bg-status-warning-bg text-status-warning border-status-warning-border",
  error: "bg-status-danger-bg text-status-danger border-status-danger-border",
};

export default function Badge({
  children,
  variant = "default",
  className = "",
  pulse = false,
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${variants[variant]} ${className}`}
    >
      {pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-ping" />}
      {children}
    </span>
  );
}
