import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Building2,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { fetchApi } from "../../services/api";
import { formatDate, formatRelativeTime } from "../../utils/date";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import CustomSelect from "../../components/ui/Select";
import JobDetailModal from "./JobDetailModal";

export default function JobsExplorer() {
  // Parse initial query params from hash: e.g. #jobs?q=...&source=...&page=...
  const getUrlParams = () => {
    const hash = window.location.hash || "";
    const queryPart = hash.includes("?") ? hash.substring(hash.indexOf("?") + 1) : "";
    return new URLSearchParams(queryPart);
  };

  const initialParams = getUrlParams();

  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(() => Math.max(1, Number(initialParams.get("page")) || 1));
  const [pageSize, setPageSize] = useState(() => [25, 50, 100].includes(Number(initialParams.get("page_size"))) ? Number(initialParams.get("page_size")) : 25);
  const [search, setSearch] = useState(() => initialParams.get("q") || "");
  const [selectedSource, setSelectedSource] = useState(() => initialParams.get("source") || "");
  const [selectedCompany, setSelectedCompany] = useState(() => initialParams.get("company") || "");

  const [availableSources, setAvailableSources] = useState([]);
  const [availableCompanies, setAvailableCompanies] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailError, setDetailError] = useState(null);

  const searchTimerRef = useRef(null);
  const searchRef = useRef(null);
  const requestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const openedDetailRef = useRef(false);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Sync state changes to URL hash
  const updateUrlState = useCallback((targetPage, querySearch, src, comp, size, jobId = null) => {
    const params = new URLSearchParams();
    if (targetPage > 1) params.set("page", String(targetPage));
    if (size !== 25) params.set("page_size", String(size));
    if (querySearch) params.set("q", querySearch);
    if (src) params.set("source", src);
    if (comp) params.set("company", comp);
    const currentPath = window.location.hash.split("?")[0];
    if (!jobId && currentPath.startsWith("#/jobs/")) jobId = decodeURIComponent(currentPath.slice(7));
    if (!jobId) jobId = getUrlParams().get("job");

    const queryStr = params.toString();
    const newHash = `/jobs${jobId ? "/" + encodeURIComponent(jobId) : ""}${queryStr ? "?" + queryStr : ""}`;
    if (window.location.hash.replace("#", "") !== newHash) {
      window.history.pushState(null, "", `#${newHash}`);
    }
  }, []);

  const loadFilters = async () => {
    try {
      const data = await fetchApi("filters");
      setAvailableSources(data.sources || []);
      setAvailableCompanies(data.companies || []);
    } catch (err) {
      console.error("Failed to load filters:", err);
    }
  };

  const loadJobs = useCallback(
    async (targetPage = page, querySearch = search, src = selectedSource, comp = selectedCompany, size = pageSize) => {
      const request = ++requestRef.current;
      setLoading(true);
      setError(null);
      updateUrlState(targetPage, querySearch, src, comp, size);
      try {
        const params = new URLSearchParams();
        params.set("page", String(targetPage));
        params.set("page_size", String(size));
        if (querySearch.trim()) params.set("q", querySearch.trim());
        if (src) params.set("source", src);
        if (comp) params.set("company", comp);

        const res = await fetchApi(`jobs?${params.toString()}`);
        if (request !== requestRef.current) return;
        setJobs(res.items || []);
        setTotal(res.total || 0);
        setPage(res.page || targetPage);
      } catch (err) {
        if (request !== requestRef.current) return;
        setError("Could not load postings. Check the local API and try again.");
        setJobs([]);
        setTotal(0);
      } finally {
        if (request === requestRef.current) setLoading(false);
      }
    },
    [page, search, selectedSource, selectedCompany, pageSize, updateUrlState]
  );

  useEffect(() => {
    loadFilters();
    const restoreRoute = () => {
      if (window.location.hash && !/^#\/?jobs(?:[/?]|$)/.test(window.location.hash)) return;
      clearTimeout(searchTimerRef.current);
      const params = getUrlParams();
      const routePage = Math.max(1, Math.floor(Number(params.get("page")) || 1));
      const routeSize = [25, 50, 100].includes(Number(params.get("page_size"))) ? Number(params.get("page_size")) : 25;
      const q = params.get("q") || "", source = params.get("source") || "", company = params.get("company") || "";
      setSearch(q); setSelectedSource(source); setSelectedCompany(company); setPage(routePage); setPageSize(routeSize);
      const path = window.location.hash.split("?")[0];
      const jobId = path.startsWith("#/jobs/") ? decodeURIComponent(path.slice(7)) : params.get("job");
      const request = ++detailRequestRef.current;
      setSelectedJob(null); setDetailError(null);
      if (jobId) fetchApi(`jobs/${encodeURIComponent(jobId)}`).then((job) => {
        if (request === detailRequestRef.current) setSelectedJob(job);
      }).catch(() => {
        if (request === detailRequestRef.current) setDetailError("Could not load this posting. Return to the list and try again.");
      });
      loadJobs(routePage, q, source, company, routeSize);
    };
    restoreRoute();
    window.addEventListener("hashchange", restoreRoute);
    const shortcuts = (event) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest("input, select, textarea, [contenteditable], [role=dialog]")) {
        event.preventDefault(); searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", shortcuts);
    return () => {
      clearTimeout(searchTimerRef.current); ++requestRef.current; ++detailRequestRef.current;
      window.removeEventListener("hashchange", restoreRoute);
      window.removeEventListener("keydown", shortcuts);
    };
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setPage(1);
      loadJobs(1, val, selectedSource, selectedCompany, pageSize);
    }, 300);
  };

  const openJobDetail = (jobSummary) => {
    openedDetailRef.current = true;
    const params = getUrlParams(); params.delete("job");
    window.history.replaceState(null, "", `#/jobs${params.size ? "?" + params : ""}`);
    window.location.hash = `/jobs/${encodeURIComponent(jobSummary.id)}${params.size ? "?" + params : ""}`;
  };

  const closeJobDetail = useCallback(() => {
    if (openedDetailRef.current) {
      openedDetailRef.current = false; window.history.back(); return;
    }
    const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
    params.delete("job");
    window.location.hash = `/jobs${params.size ? "?" + params : ""}`;
  }, []);

  return (
    <div className="space-y-6" aria-busy={loading}>
      <h1 className="text-[32px] font-semibold">Job postings</h1>
      <p role="status" className="text-sm text-text-muted">{loading ? "Updating postings…" : `${total.toLocaleString()} postings available`}</p>
      {/* Top Filter & Toolbar */}
      <Card className="jobs-toolbar sticky top-[var(--app-header-height,72px)] z-30 p-5 space-y-4">
        <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:items-center justify-between">
          {/* Search Input */}
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-text-dim">
              <Search className="w-4 h-4" />
            </div>
            <input
              ref={searchRef}
              type="search"
              aria-label="Search job postings by title or company"
              value={search}
              onChange={handleSearchChange}
              placeholder="Search title or company · / to focus"
              className="w-full pl-10 pr-4 py-2.5 min-h-[44px] bg-bg-surface border border-border-subtle rounded-xl text-sm text-text-main placeholder:text-text-dim focus:outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus transition-colors"
            />
          </div>

          {/* Filters & Actions */}
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-3">
            <CustomSelect
              aria-label="Filter by source board"
              value={selectedSource}
              onChange={(val) => {
                setSelectedSource(val);
                setPage(1);
                loadJobs(1, search, val, selectedCompany, pageSize);
              }}
              options={[
                { value: "", label: "All Sources" },
                ...availableSources.map((s) => ({ value: s, label: s })),
              ]}
              icon={Filter}
              className="w-full sm:w-44"
            />

            <CustomSelect
              aria-label="Filter by company"
              value={selectedCompany}
              onChange={(val) => {
                setSelectedCompany(val);
                setPage(1);
                loadJobs(1, search, selectedSource, val, pageSize);
              }}
              options={[
                { value: "", label: "All Companies" },
                ...availableCompanies.map((c) => ({ value: c, label: c })),
              ]}
              icon={Building2}
              className="w-full sm:w-48"
            />

            <CustomSelect
              aria-label="Results per page"
              value={pageSize}
              onChange={(val) => {
                const num = Number(val);
                setPageSize(num);
                setPage(1);
                loadJobs(1, search, selectedSource, selectedCompany, num);
              }}
              options={[
                { value: 25, label: "25 / page" },
                { value: 50, label: "50 / page" },
                { value: 100, label: "100 / page" },
              ]}
              className="w-32"
              align="right"
            />

            <Button
              variant="secondary"
              size="icon"
              onClick={() => loadJobs(page)}
              title="Refresh table"
              aria-label="Refresh job table"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-accent" : ""}`} />
            </Button>
          </div>
        </div>

        {detailError && (
          <div role="alert" className="p-3 rounded-xl bg-status-danger-bg border border-status-danger-border text-xs text-status-danger flex items-center justify-between">
            <span>{detailError}</span>
            <button
              type="button"
              onClick={() => setDetailError(null)}
              className="text-xs font-semibold cursor-pointer underline ml-2"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Status Bar */}
        <div className="flex items-center justify-between text-xs text-text-muted pt-2 border-t border-border-subtle">
          <div>
            Showing <span className="text-text-main font-semibold">{total.toLocaleString()}</span> total jobs
            {(search || selectedSource || selectedCompany) && (
              <span className="text-accent ml-1 font-medium">(filtered)</span>
            )}
          </div>
          <div>
            Page <span className="text-text-main font-semibold">{page}</span> of{" "}
            <span className="text-text-main font-semibold">{totalPages}</span>
          </div>
        </div>
      </Card>

      {/* Jobs Table */}
      <Card className="overflow-hidden">
        {error ? (
          <div className="p-8 text-center space-y-3">
            <p className="text-status-danger font-medium">{error}</p>
            <Button variant="secondary" onClick={() => loadJobs(page)}>
              Try Again
            </Button>
          </div>
        ) : loading && jobs.length === 0 ? (
          <div className="p-16 flex flex-col items-center justify-center text-text-muted space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-accent" />
            <span className="text-sm">Fetching job postings...</span>
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-16 text-center space-y-2">
            <p className="text-text-main font-medium">No job postings found</p>
            <p className="text-xs text-text-dim">
              Try adjusting your search criteria or run a scraper to collect jobs.
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="jobs-table w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="bg-bg-surface-elevated border-b border-border-subtle text-xs font-semibold uppercase tracking-wider text-text-muted">
                    <th className="py-3.5 px-6">Job Title & Company</th>
                    <th className="py-3.5 px-4">Source Board</th>
                    <th className="py-3.5 px-4">Posted Date</th>
                    <th className="py-3.5 px-4">Scraped</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {jobs.map((job) => (
                    <tr
                      key={job.id}
                      tabIndex={0}
                      aria-label={`View details for ${job.title} at ${job.company_name}`}
                      className="hover:bg-bg-surface-elevated/80 transition-colors group cursor-pointer focus-visible:outline-none focus-visible:bg-bg-surface-elevated focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-inset"
                      onClick={() => openJobDetail(job)}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === "j" || e.key === "k") {
                          e.preventDefault();
                          (e.key === "j" ? e.currentTarget.nextElementSibling : e.currentTarget.previousElementSibling)?.focus();
                        }
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openJobDetail(job);
                        }
                      }}
                    >
                      <td className="py-4 px-6">
                        <div className="font-semibold text-text-main group-hover:text-accent transition-colors leading-snug">
                          {job.title}
                        </div>
                        <div className="flex items-center gap-1.5 text-xs text-text-muted mt-1">
                          <Building2 className="w-3.5 h-3.5 text-text-dim" />
                          <span>{job.company_name}</span>
                        </div>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap">
                        <Badge variant="neutral">{job.source}</Badge>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap text-xs text-text-muted">
                        <div className="font-medium text-text-main">{formatRelativeTime(job.posted_at)}</div>
                        <div className="text-text-dim text-[11px]">{formatDate(job.posted_at)}</div>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap text-xs text-text-dim">
                        {formatRelativeTime(job.scraped_at)}
                      </td>
                      <td className="py-4 px-6 text-right whitespace-nowrap">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            openJobDetail(job);
                          }}
                        >
                          View Details
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="jobs-pagination flex flex-wrap items-center justify-between p-4 bg-bg-surface-elevated/40 border-t border-border-subtle">
              <div className="text-xs text-text-muted">
                Showing <span className="font-semibold text-text-main">{(page - 1) * pageSize + 1}</span>{" "}
                to{" "}
                <span className="font-semibold text-text-main">
                  {Math.min(page * pageSize, total)}
                </span>{" "}
                of <span className="font-semibold text-text-main">{total.toLocaleString()}</span>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1 || loading}
                  onClick={() => {
                    const prev = page - 1;
                    setPage(prev);
                    loadJobs(prev);
                  }}
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  Previous
                </Button>

                <span className="text-xs text-text-muted px-2 font-mono">
                  {page} / {totalPages}
                </span>

                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages || loading}
                  onClick={() => {
                    const next = page + 1;
                    setPage(next);
                    loadJobs(next);
                  }}
                >
                  Next
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      {selectedJob && (
        <JobDetailModal job={selectedJob} onClose={closeJobDetail} />
      )}
    </div>
  );
}
