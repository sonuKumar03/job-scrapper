export function formatDate(val) {
  if (!val) return "—";
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) return String(val);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(val);
  }
}

export function formatRelativeTime(val) {
  if (!val) return "—";
  try {
    const date = new Date(val);
    if (isNaN(date.getTime())) return "—";
    const now = new Date();
    const elapsed = now.getTime() - date.getTime();
    const diffSec = Math.floor(Math.abs(elapsed) / 1000);
    const relative = (count, unit) => elapsed < 0 ? `in ${count}${unit}` : `${count}${unit} ago`;
    if (diffSec < 60) return "just now";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return relative(diffMin, "m");
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24) return relative(diffHrs, "h");
    const diffDays = Math.floor(diffHrs / 24);
    if (diffDays < 30) return relative(diffDays, "d");
    if (diffDays < 365) return relative(Math.floor(diffDays / 30), "mo");
    return relative(Math.floor(diffDays / 365), "y");
  } catch {
    return String(val);
  }
}
