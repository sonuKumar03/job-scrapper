import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";

export default function CustomSelect({
  value,
  onChange,
  options,
  placeholder = "Select...",
  icon: Icon,
  className = "",
  align = "left",
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find((opt) =>
    typeof opt === "object" ? opt.value === value : opt === value
  );

  const selectedLabel = selectedOption
    ? typeof selectedOption === "object"
      ? selectedOption.label
      : selectedOption
    : placeholder;

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between gap-2.5 px-3.5 py-2.5 bg-bg-surface hover:bg-bg-surface-elevated active:bg-bg-surface-elevated border border-border-subtle hover:border-border-muted rounded-xl text-xs font-medium text-text-main transition-all cursor-pointer shadow-sm text-left"
      >
        <div className="flex items-center gap-2 truncate">
          {Icon && <Icon className="w-3.5 h-3.5 text-text-dim shrink-0" />}
          <span className="truncate">{selectedLabel}</span>
        </div>
        <ChevronDown
          className={`w-3.5 h-3.5 text-text-dim shrink-0 transition-transform duration-200 ${
            isOpen ? "rotate-180 text-accent" : ""
          }`}
        />
      </button>

      {isOpen && (
        <div
          className={`absolute z-50 mt-1.5 min-w-[160px] max-h-64 overflow-y-auto bg-bg-surface border border-border-subtle rounded-xl shadow-2xl p-1.5 space-y-0.5 animate-in fade-in zoom-in-95 duration-150 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {options.map((opt) => {
            const optVal = typeof opt === "object" ? opt.value : opt;
            const optLabel = typeof opt === "object" ? opt.label : opt;
            const isSelected = optVal === value;

            return (
              <button
                key={String(optVal)}
                type="button"
                onClick={() => {
                  onChange(optVal);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left cursor-pointer ${
                  isSelected
                    ? "bg-accent-subtle text-accent font-semibold"
                    : "text-text-muted hover:bg-bg-surface-elevated hover:text-text-main"
                }`}
              >
                <span className="truncate">{optLabel}</span>
                {isSelected && <Check className="w-3.5 h-3.5 text-accent shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
