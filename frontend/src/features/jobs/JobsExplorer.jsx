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
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [selectedSource, setSelectedSource] = useState("");
  const [selectedCompany, setSelectedCompany] = useState("");

  const [availableSources, setAvailableSources] = useState([]);
  const [availableCompanies, setAvailableCompanies] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);

  const searchTimerRef = useRef(null);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

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
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set("page", String(targetPage));
        params.set("page_size", String(size));
        if (querySearch.trim()) params.set("q", querySearch.trim());
        if (src) params.set("source", src);
        if (comp) params.set("company", comp);

        const res = await fetchApi(`jobs?${params.toString()}`);
        setJobs(res.items || []);
        setTotal(res.total || 0);
        setPage(res.page || targetPage);
      } catch (err) {
        setError(err.message || "Failed to load jobs");
        setJobs([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [page, search, selectedSource, selectedCompany, pageSize]
  );

  useEffect(() => {
    loadFilters();
    loadJobs(1, "", "", "", 25);
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

  const openJobDetail = async (jobSummary) => {
    try {
      const full = await fetchApi(`jobs/${jobSummary.id}`);
      setSelectedJob(full);
    } catch (err) {
      alert("Error loading job details: " + err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Filter & Toolbar */}
      <Card className="p-5 space-y-4">
        <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:items-center justify-between">
          {/* Search Input */}
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <Search className="w-4 h-4" />
            </div>
            <input
              type="search"
              value={search}
              onChange={handleSearchChange}
              placeholder="Search by title or company (e.g. 'Backend Engineer', 'Apple')..."
              className="w-full pl-10 pr-4 py-2.5 bg-slate-950/80 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
            />
          </div>

          {/* Filters & Actions */}
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-3">
            <CustomSelect
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
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-emerald-400" : ""}`} />
            </Button>
          </div>
        </div>

        {/* Status Bar */}
        <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-slate-800/80">
          <div>
            Showing <span className="text-white font-semibold">{total.toLocaleString()}</span> total jobs
            {(search || selectedSource || selectedCompany) && (
              <span className="text-emerald-400 ml-1">(filtered)</span>
            )}
          </div>
          <div>
            Page <span className="text-slate-200 font-semibold">{page}</span> of{" "}
            <span className="text-slate-200 font-semibold">{totalPages}</span>
          </div>
        </div>
      </Card>

      {/* Jobs Table */}
      <Card>
        {error ? (
          <div className="p-8 text-center space-y-3">
            <p className="text-rose-400 font-medium">{error}</p>
            <Button variant="secondary" onClick={() => loadJobs(page)}>
              Try Again
            </Button>
          </div>
        ) : loading && jobs.length === 0 ? (
          <div className="p-16 flex flex-col items-center justify-center text-slate-400 space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            <span className="text-sm">Fetching job postings...</span>
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-16 text-center space-y-2">
            <p className="text-slate-300 font-medium">No job postings found</p>
            <p className="text-xs text-slate-500">
              Try adjusting your search criteria or run a scraper to collect jobs.
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="bg-slate-950/50 border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    <th className="py-3.5 px-6">Job Title & Company</th>
                    <th className="py-3.5 px-4">Source Board</th>
                    <th className="py-3.5 px-4">Posted Date</th>
                    <th className="py-3.5 px-4">Scraped</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {jobs.map((job) => (
                    <tr
                      key={job.id}
                      className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                      onClick={() => openJobDetail(job)}
                    >
                      <td className="py-4 px-6">
                        <div className="font-semibold text-white group-hover:text-emerald-400 transition-colors leading-snug">
                          {job.title}
                        </div>
                        <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-1">
                          <Building2 className="w-3.5 h-3.5 text-slate-500" />
                          <span>{job.company_name}</span>
                        </div>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap">
                        <Badge variant="success">{job.source}</Badge>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap text-xs text-slate-300">
                        <div>{formatRelativeTime(job.posted_at)}</div>
                        <div className="text-slate-500 text-[11px]">{formatDate(job.posted_at)}</div>
                      </td>
                      <td className="py-4 px-4 whitespace-nowrap text-xs text-slate-400">
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
                          className="hover:bg-emerald-600 hover:text-white hover:border-emerald-500"
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
            <div className="flex items-center justify-between p-4 bg-slate-950/60 border-t border-slate-800">
              <div className="text-xs text-slate-400">
                Showing <span className="font-semibold text-slate-200">{(page - 1) * pageSize + 1}</span>{" "}
                to{" "}
                <span className="font-semibold text-slate-200">
                  {Math.min(page * pageSize, total)}
                </span>{" "}
                of <span className="font-semibold text-slate-200">{total.toLocaleString()}</span>
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

                <span className="text-xs text-slate-400 px-2 font-mono">
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
        <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />
      )}
    </div>
  );
}
