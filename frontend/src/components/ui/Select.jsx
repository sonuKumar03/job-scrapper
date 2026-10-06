import React, { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";

export default function CustomSelect({ value, onChange, options, placeholder = "Select...", icon: Icon, className = "", "aria-label": ariaLabel }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const inputRef = useRef(null);
  const id = useId();
  const items = options.map((option) => typeof option === "object" ? option : { value: option, label: option });
  const selected = items.find((item) => String(item.value) === String(value));
  const filtered = items.filter((item) => item.label.toLowerCase().includes(query.toLowerCase()));
  const label = ariaLabel || placeholder;

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const dismiss = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, id]);

  const close = () => { setOpen(false); triggerRef.current?.focus(); };
  const choose = (item) => { onChange(item.value); close(); };
  const show = (last = false) => {
    setQuery("");
    const index = items.findIndex((item) => String(item.value) === String(value));
    setActive(last ? items.length - 1 : Math.max(0, index));
    setOpen(true);
  };

  return (
    <div ref={rootRef} className={`relative min-w-0 ${className}`}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
      <button ref={triggerRef} type="button" aria-label={label} aria-haspopup="listbox"
        aria-expanded={open} aria-controls={open ? `${id}-list` : undefined}
        onClick={() => open ? close() : show()}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); show(event.key === "ArrowUp"); }
        }}
        className="flex items-center gap-2 w-full min-h-[44px] px-3 rounded-md border border-border-subtle bg-bg-surface text-text-main text-sm text-left hover:border-border-muted">
        {Icon && <Icon aria-hidden="true" className="w-4 h-4 text-text-muted shrink-0" />}
        <span className="flex-1 truncate">{selected?.label || placeholder}</span>
        <ChevronDown aria-hidden="true" className="w-4 h-4 text-text-muted shrink-0" />
      </button>
      {open && <div className="absolute right-0 top-full mt-2 z-50 w-[max(100%,min(320px,calc(100vw-64px)))] rounded-md border border-border-muted bg-bg-surface shadow-lg overflow-hidden">
        <div className="relative p-2 border-b border-border-subtle">
          <Search aria-hidden="true" className="absolute left-5 top-5 w-4 h-4 text-text-muted pointer-events-none" />
          <input ref={inputRef} role="combobox" aria-label={`Search ${label.toLowerCase()}`} aria-autocomplete="list"
            aria-expanded="true" aria-controls={`${id}-list`}
            aria-activedescendant={filtered[active] ? `${id}-option-${active}` : undefined}
            value={query} placeholder="Type to filter…"
            onChange={(event) => { setQuery(event.target.value); setActive(0); }}
            onKeyDown={(event) => {
              if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
              else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                setActive((index) => event.key === "Home" ? 0 : event.key === "End" ? filtered.length - 1 : Math.max(0, Math.min(filtered.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
              } else if (event.key === "Enter") {
                event.preventDefault(); if (filtered[active]) choose(filtered[active]);
              }
            }}
            className="w-full min-h-[44px] pl-9 pr-3 rounded border border-border-subtle bg-bg-surface text-text-main text-sm placeholder:text-text-muted" />
        </div>
        <div id={`${id}-list`} role="listbox" aria-label={label} className="max-h-64 overflow-y-auto p-1">
          {filtered.map((item, index) => <div key={String(item.value)} id={`${id}-option-${index}`} role="option"
            aria-selected={String(item.value) === String(value)}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => choose(item)} onPointerMove={() => setActive(index)}
            className={`flex items-center justify-between gap-3 min-h-[44px] px-3 py-2 rounded text-sm cursor-pointer ${index === active ? "bg-bg-surface-elevated text-text-main" : "text-text-muted"}`}>
            <span className="min-w-0 break-words">{item.label}</span>
            {String(item.value) === String(value) && <Check aria-hidden="true" className="w-4 h-4 text-accent shrink-0" />}
          </div>)}
          {!filtered.length && <p role="status" className="p-3 text-sm text-text-muted">No matching options</p>}
        </div>
      </div>}
    </div>
  );
}
