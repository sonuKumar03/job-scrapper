import React from "react";

export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`bg-bg-surface border border-border-subtle rounded-2xl shadow-xl overflow-hidden ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
