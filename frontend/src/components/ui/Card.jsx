import React from "react";

export default function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`bg-bg-surface border border-border-subtle rounded-md ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
