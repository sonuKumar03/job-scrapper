import React from "react";

export default function CustomSelect({ value, onChange, options, placeholder = "Select...", icon: Icon, className = "", "aria-label": ariaLabel }) {
  return (
    <div className={`relative min-w-0 ${className}`}>
      {Icon && <Icon aria-hidden="true" className="absolute left-3 top-3.5 w-4 h-4 text-text-muted pointer-events-none" />}
      <select aria-label={ariaLabel || placeholder} value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`w-full min-h-[44px] rounded-md border border-border-subtle bg-bg-surface text-text-main text-sm pr-3 ${Icon ? "pl-9" : "pl-3"}`}>
        {options.map((option) => {
          const item = typeof option === "object" ? option : { value: option, label: option };
          return <option key={String(item.value)} value={item.value}>{item.label}</option>;
        })}
      </select>
    </div>
  );
}
