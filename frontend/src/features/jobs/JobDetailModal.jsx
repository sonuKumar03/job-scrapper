import React, { useState } from "react";
import {
  ExternalLink,
  ChevronDown,
  X,
  Building2,
  Calendar,
  Clock,
  Tag,
  ShieldCheck,
  Layers,
  MapPin,
  Briefcase,
  DollarSign,
  Award,
  FileText,
} from "lucide-react";
import { formatDate, formatRelativeTime } from "../../utils/date";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";

export default function JobDetailModal({ job, onClose }) {
  const [showRawMeta, setShowRawMeta] = useState(false);

  if (!job) return null;

  const attributes = job.attributes || {};
  const sightings = job.sightings || [];

  const location = attributes.location || "Not specified";
  const workArrangement = attributes.work_arrangement || "Not specified";
  const experienceYearsMin = attributes.experience_years_min;
  const experienceYearsMax = attributes.experience_years_max;
  const experienceText =
    experienceYearsMin || experienceYearsMax
      ? `${experienceYearsMin ?? "0"} - ${experienceYearsMax ?? "+"} yrs`
      : null;

  const techStack = Array.isArray(attributes.tech_stack)
    ? attributes.tech_stack
    : typeof attributes.tech_stack === "string"
    ? attributes.tech_stack.split(",").map((s) => s.trim())
    : [];

  const salaryMin = attributes.salary_min;
  const salaryMax = attributes.salary_max;
  const salaryCurrency = attributes.salary_currency || "$";
  const salaryText =
    salaryMin || salaryMax
      ? `${salaryCurrency}${salaryMin ? Number(salaryMin).toLocaleString() : ""}${
          salaryMax ? " - " + salaryCurrency + Number(salaryMax).toLocaleString() : ""
        }`
      : null;

  const knownKeys = new Set([
    "location",
    "work_arrangement",
    "experience_years_min",
    "experience_years_max",
    "tech_stack",
    "salary_min",
    "salary_max",
    "salary_currency",
  ]);
  const otherAttributes = Object.entries(attributes).filter(
    ([k]) => !knownKeys.has(k)
  );

  const rawMetadata = { ...job };
  delete rawMetadata.title;
  delete rawMetadata.company_name;
  delete rawMetadata.description_text;
  delete rawMetadata.attributes;
  delete rawMetadata.sightings;
  delete rawMetadata.posted_at;
  delete rawMetadata.scraped_at;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 lg:p-8 animate-in fade-in duration-200">
      <button
        type="button"
        aria-label="Close dialog overlay"
        className="fixed inset-0 w-full h-full cursor-default bg-transparent border-0"
        onClick={onClose}
      />

      <div className="relative z-10 w-full max-w-5xl max-h-[92vh] bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-5 bg-slate-900/90 border-b border-slate-800/80 flex items-start justify-between gap-4">
          <div className="space-y-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="success">{job.source}</Badge>
              {job.source_job_id && (
                <span className="text-xs font-mono text-slate-500">
                  ID: {job.source_job_id}
                </span>
              )}
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight leading-snug truncate">
              {job.title}
            </h2>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
              <div className="flex items-center gap-1.5 text-slate-200 font-semibold">
                <Building2 className="w-4 h-4 text-emerald-400" />
                <span>{job.company_name}</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <Calendar className="w-3.5 h-3.5 text-slate-500" />
                <span>Posted: {formatDate(job.posted_at)} ({formatRelativeTime(job.posted_at)})</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-500">
                <Clock className="w-3.5 h-3.5" />
                <span>Scraped: {formatDate(job.scraped_at)}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {job.source_url && (
              <a
                href={job.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="primary" size="md">
                  <span>Original Listing</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Button>
              </a>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              title="Close modal"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Key Factor Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3">
              <div className="w-8 h-8 rounded-xl bg-slate-800/80 flex items-center justify-center shrink-0 text-slate-300">
                <MapPin className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Location</div>
                <div className="text-xs font-semibold text-slate-200 mt-0.5 truncate">{location}</div>
              </div>
            </div>

            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3">
              <div className="w-8 h-8 rounded-xl bg-slate-800/80 flex items-center justify-center shrink-0 text-slate-300">
                <Briefcase className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Arrangement</div>
                <div className="text-xs font-semibold text-slate-200 mt-0.5 capitalize truncate">{workArrangement}</div>
              </div>
            </div>

            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3">
              <div className="w-8 h-8 rounded-xl bg-slate-800/80 flex items-center justify-center shrink-0 text-slate-300">
                <Award className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Experience</div>
                <div className="text-xs font-semibold text-slate-200 mt-0.5 truncate">
                  {experienceText || "Not specified"}
                </div>
              </div>
            </div>

            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 flex items-start gap-3">
              <div className="w-8 h-8 rounded-xl bg-slate-800/80 flex items-center justify-center shrink-0 text-slate-300">
                <DollarSign className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="min-w-0">
                <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Compensation</div>
                <div className="text-xs font-semibold text-slate-200 mt-0.5 truncate">
                  {salaryText || "Unlisted"}
                </div>
              </div>
            </div>
          </div>

          {/* Tech Stack Chips */}
          {techStack.length > 0 && (
            <div className="p-4 rounded-2xl bg-slate-950/40 border border-slate-800/80 space-y-2">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Tag className="w-3.5 h-3.5 text-emerald-400" />
                Detected Tech Stack & Skills
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {techStack.map((tech, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800/90 text-slate-200 border border-slate-700/60"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Other Attributes */}
          {otherAttributes.length > 0 && (
            <div className="p-4 rounded-2xl bg-slate-950/40 border border-slate-800/80 space-y-2.5">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Additional Classification Attributes
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {otherAttributes.map(([key, val]) => (
                  <div key={key} className="text-xs p-2 rounded-xl bg-slate-900 border border-slate-800/80">
                    <span className="text-slate-500 block font-medium capitalize">{key.replace(/_/g, " ")}</span>
                    <span className="text-slate-200 font-semibold mt-0.5 block truncate">
                      {typeof val === "object" ? JSON.stringify(val) : String(val)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Full Job Description */}
          <div className="space-y-2.5">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              Full Job Description
            </div>
            <div className="p-5 rounded-2xl bg-slate-950/60 border border-slate-800/80 text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans selection:bg-emerald-900/60">
              {job.description_text || "No description provided for this posting."}
            </div>
          </div>

          {/* Multi-Source Sightings */}
          {sightings.length > 0 && (
            <div className="space-y-2.5">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-4 h-4 text-emerald-400" />
                Aggregated Sightings ({sightings.length})
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {sightings.map((sighting, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 font-bold rounded-lg bg-slate-800 text-slate-200">
                        {sighting.source}
                      </span>
                      <span className="text-slate-500 font-mono">ID: {sighting.source_job_id}</span>
                    </div>
                    <span className="text-slate-400 text-[11px]">
                      {sighting.last_seen_at ? formatRelativeTime(sighting.last_seen_at) : "Seen"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Raw Metadata Details */}
          <div className="border-t border-slate-800/80 pt-4">
            <button
              type="button"
              onClick={() => setShowRawMeta(!showRawMeta)}
              className="flex items-center justify-between w-full py-1 text-xs font-medium text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
            >
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-slate-600" />
                Deduplication Signatures & Raw Cryptographic Hashes
              </span>
              <ChevronDown
                className={`w-4 h-4 transition-transform duration-200 ${showRawMeta ? "rotate-180" : ""}`}
              />
            </button>

            {showRawMeta && (
              <div className="mt-3 p-4 rounded-2xl bg-slate-950 font-mono text-xs text-slate-300 border border-slate-800 space-y-1.5 overflow-x-auto">
                {Object.entries(rawMetadata).map(([k, v]) => (
                  <div key={k} className="flex flex-col sm:flex-row sm:gap-4 py-1 border-b border-slate-900 last:border-0">
                    <span className="text-slate-500 min-w-48 font-semibold">{k}:</span>
                    <span className="text-slate-300 break-all">{v !== null && v !== undefined ? String(v) : "null"}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
