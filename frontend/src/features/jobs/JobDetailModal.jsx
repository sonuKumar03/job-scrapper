import React, { useEffect, useRef } from "react";
import { formatDate } from "../../utils/date";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";

export default function JobDetailModal({ job, onClose }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close(); document.body.style.overflow = originalOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  let safeUrl = null;
  try {
    const url = new URL(job.source_url);
    if (["http:", "https:"].includes(url.protocol)) safeUrl = url.href;
  } catch { /* Missing or invalid source URLs are shown as unavailable. */ }
  const metadata = Object.entries(job).filter(([key]) => !["title", "company_name", "description_text", "attributes", "sightings"].includes(key));
  const display = (value) => value == null ? "Not stored" : typeof value === "object" ? JSON.stringify(value) : String(value);
  return (
    <dialog ref={dialogRef} aria-labelledby="job-dialog-title" onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="m-auto w-[calc(100%-32px)] max-w-5xl max-h-[90vh] overflow-y-auto rounded-md border border-border-subtle bg-bg-surface text-text-main p-0 backdrop:bg-black/50">
      <div className="p-4 sm:p-8 space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border-subtle pb-4">
          <div className="min-w-0 flex-1">
            <Badge variant="neutral">{job.source}</Badge>
            <h2 id="job-dialog-title" className="text-2xl font-semibold mt-2 break-words">{job.title}</h2>
            <p className="text-text-muted mt-1">{job.company_name}</p>
            <p className="text-sm text-text-muted mt-2">Posted {formatDate(job.posted_at)} · Collected {formatDate(job.scraped_at)}</p>
          </div>
          <Button onClick={onClose}>Back to postings</Button>
        </header>
        <section className="space-y-2">
          <h3 className="font-semibold">Dataset record</h3>
          <p className="text-sm text-text-muted">Canonical signatures identify equivalent postings. Content hashes match exact text; SimHash detects similar descriptions. Sightings record repeated observations across sources.</p>
          <dl className="grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-x-4 text-sm">
            {metadata.map(([key, value]) => <React.Fragment key={key}>
              <dt className="text-text-muted py-2 border-t border-border-subtle">{key.replaceAll("_", " ")}</dt>
              <dd className="font-mono break-all py-2 border-t border-border-subtle">{display(value)}</dd>
            </React.Fragment>)}
          </dl>
          {safeUrl ? <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center min-h-[44px] text-accent underline">Open source listing ↗</a> : <p className="text-sm text-text-muted">Source link unavailable</p>}
        </section>
        <section className="space-y-2">
          <h3 className="font-semibold">Full description</h3>
          <p className="max-w-[75ch] whitespace-pre-wrap break-words leading-relaxed">{job.description_text || "No description stored."}</p>
        </section>
        <section className="border-t border-border-subtle pt-4 space-y-2">
          <h3 className="font-semibold">Classification attributes</h3>
          {Object.keys(job.attributes || {}).length ? <dl className="grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-3 text-sm">
            {Object.entries(job.attributes).map(([key, value]) => <React.Fragment key={key}><dt className="text-text-muted">{key.replaceAll("_", " ")}</dt><dd className="break-words">{display(value)}</dd></React.Fragment>)}
          </dl> : <p className="text-text-muted text-sm">No classification attributes stored.</p>}
        </section>
        <section className="border-t border-border-subtle pt-4 space-y-3">
          <h3 className="font-semibold">Sightings ({job.sightings?.length || 0})</h3>
          {(job.sightings || []).map((sighting, index) => <dl key={index} className="text-sm border-t border-border-subtle py-3 grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-2">
            {Object.entries(sighting).map(([key, value]) => <React.Fragment key={key}><dt className="text-text-muted">{key.replaceAll("_", " ")}</dt><dd className="break-all">{display(value)}</dd></React.Fragment>)}
          </dl>)}
        </section>
      </div>
    </dialog>
  );
}
