import React, { useState, useEffect } from "react";
import {
  Play,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { fetchApi } from "../../services/api";
import { formatDate, formatRelativeTime } from "../../utils/date";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";

export default function ScrapeRuns() {
  const [availableSources, setAvailableSources] = useState([]);
  const [selectedSources, setSelectedSources] = useState([]);
  const [days, setDays] = useState(1);

  const [runs, setRuns] = useState([]);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const [selectedRun, setSelectedRun] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState(false);

  const loadSession = async () => {
    try {
      const data = await fetchApi("session");
      const srcs = data.sources || [];
      setAvailableSources(srcs);
      if (srcs.length > 0) {
        setSelectedSources([srcs[0]]);
      }
    } catch (err) {
      console.error("Failed to load session/sources:", err);
    }
  };

  const loadRuns = async (targetPage = page) => {
    setLoadingRuns(true);
    try {
      const data = await fetchApi(`runs?page=${targetPage}&page_size=${pageSize}`);
      setRuns(data.items || []);
      setPage(data.page || targetPage);
    } catch (err) {
      console.error("Failed to load runs:", err);
    } finally {
      setLoadingRuns(false);
    }
  };

  const refreshSelectedRun = async (runId) => {
    try {
      const detail = await fetchApi(`runs/${runId}`);
      setSelectedRun(detail);
    } catch (err) {
      console.error("Failed to refresh run details:", err);
    }
  };

  const startScrape = async () => {
    if (selectedSources.length === 0) {
      setStatusMessage("Select at least one source connector.");
      setStatusError(true);
      return;
    }

    setIsSubmitting(true);
    setStatusMessage("Dispatching scrape task...");
    setStatusError(false);

    try {
      const res = await fetchApi("runs", {
        method: "POST",
        body: JSON.stringify({
          sources: selectedSources,
          days: Number(days),
        }),
      });

      setStatusMessage("Scrape started successfully!");
      setStatusError(false);

      await loadRuns(1);
      if (res.id) {
        await refreshSelectedRun(res.id);
      }
    } catch (err) {
      setStatusMessage(err.message || "Failed to start scrape run");
      setStatusError(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleSource = (source) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const isAnyRunning =
    selectedRun?.status === "running" || runs.some((r) => r.status === "running");

  useEffect(() => {
    loadSession();
    loadRuns(1);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      if (isAnyRunning) {
        loadRuns(page);
        if (selectedRun?.id) {
          refreshSelectedRun(selectedRun.id);
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [isAnyRunning, page, selectedRun?.id]);

  const getStatusBadgeVariant = (status) => {
    if (status === "completed") return "success";
    if (status === "running") return "running";
    return "error";
  };

  return (
    <div className="space-y-8">
      {/* Trigger Scrape Card */}
      <Card className="p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Play className="w-5 h-5 text-emerald-400" />
              Trigger Scrape Run
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Select target platforms and cutoff days. Note: ATS connectors fetch all active openings.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSelectedSources([...availableSources])}
            >
              Select All
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSelectedSources([])}
            >
              Clear
            </Button>
          </div>
        </div>

        {/* Source Grid */}
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 block">
            Available Connectors ({selectedSources.length}/{availableSources.length} selected)
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
            {availableSources.map((source) => {
              const isSelected = selectedSources.includes(source);
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => toggleSource(source)}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium border transition-all text-left cursor-pointer ${
                    isSelected
                      ? "bg-emerald-950/70 border-emerald-600/80 text-emerald-300 shadow-sm shadow-emerald-950"
                      : "bg-slate-950/60 border-slate-800 text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                  }`}
                >
                  <span className="truncate">{source}</span>
                  {isSelected && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 ml-1.5" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Form Actions */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-end justify-between gap-4 pt-2">
          <div className="flex items-center gap-3">
            <div>
              <label
                htmlFor="days-input"
                className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-1.5"
              >
                Days Window
              </label>
              <input
                id="days-input"
                type="number"
                min="1"
                max="365"
                value={days}
                onChange={(e) => setDays(e.target.value)}
                className="w-28 px-3 py-2.5 bg-slate-950/80 border border-slate-800 rounded-xl text-sm text-slate-100 focus:outline-none focus:border-emerald-500 font-mono"
              />
            </div>
            <div className="text-[11px] text-slate-500 max-w-xs pt-4">
              General job boards filter postings created in the last {days} {days == 1 ? "day" : "days"}.
            </div>
          </div>

          <div className="flex items-center gap-3">
            {statusMessage && (
              <span
                className={`text-xs font-medium ${
                  statusError ? "text-rose-400" : "text-emerald-400"
                }`}
              >
                {statusMessage}
              </span>
            )}
            <Button
              variant="primary"
              size="lg"
              loading={isSubmitting}
              disabled={isSubmitting || isAnyRunning || selectedSources.length === 0}
              onClick={startScrape}
            >
              <Play className="w-4 h-4 fill-white" />
              <span>{isAnyRunning ? "Scraping Active..." : "Start Scrape"}</span>
            </Button>
          </div>
        </div>
      </Card>

      {/* Selected Run Details */}
      {selectedRun && (
        <Card className="p-6 space-y-6 animate-in fade-in duration-150">
          <div className="flex items-start justify-between pb-4 border-b border-slate-800">
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-base font-bold text-white">Execution Inspector</h3>
                <Badge variant={getStatusBadgeVariant(selectedRun.status)}>
                  {selectedRun.status}
                </Badge>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-1">ID: {selectedRun.id}</p>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSelectedRun(null)}
            >
              Close Detail
            </Button>
          </div>

          {/* Stats Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <span className="text-[11px] text-slate-500 uppercase font-semibold">Started</span>
              <div className="text-xs font-medium text-slate-200 mt-0.5">
                {formatDate(selectedRun.started_at)}
              </div>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <span className="text-[11px] text-slate-500 uppercase font-semibold">Finished</span>
              <div className="text-xs font-medium text-slate-200 mt-0.5">
                {formatDate(selectedRun.finished_at)}
              </div>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <span className="text-[11px] text-slate-500 uppercase font-semibold">Days Cutoff</span>
              <div className="text-xs font-medium text-slate-200 mt-0.5">
                {selectedRun.days} days
              </div>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80">
              <span className="text-[11px] text-slate-500 uppercase font-semibold">Sources</span>
              <div className="text-xs font-medium text-slate-200 mt-0.5 truncate">
                {selectedRun.sources?.join(", ")}
              </div>
            </div>
          </div>

          {/* Connectors breakdown */}
          {selectedRun.results && Object.keys(selectedRun.results).length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Connector Execution Results
              </h4>
              <div className="space-y-3">
                {Object.entries(selectedRun.results).map(([sourceName, stats]) => (
                  <div
                    key={sourceName}
                    className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white">{sourceName}</span>
                        <Badge variant={getStatusBadgeVariant(stats.status || "completed")}>
                          {stats.status || "done"}
                        </Badge>
                        {stats.truncated && (
                          <Badge variant="warning">
                            <AlertTriangle className="w-3 h-3 mr-1" />
                            Incomplete Coverage
                          </Badge>
                        )}
                      </div>

                      {stats.found !== undefined && (
                        <div className="text-xs text-slate-400 flex items-center gap-3">
                          <span className="text-slate-300 font-semibold">
                            {stats.found.toLocaleString()} found
                          </span>
                          <span className="text-emerald-400 font-semibold">
                            {stats.inserted.toLocaleString()} inserted
                          </span>
                          <span className="text-slate-500">
                            {stats.skipped.toLocaleString()} skipped
                          </span>
                        </div>
                      )}
                    </div>

                    {stats.errors && stats.errors.length > 0 && (
                      <div className="p-2.5 rounded bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 space-y-1">
                        {stats.errors.map((err, i) => (
                          <div key={i} className="flex items-start gap-1.5">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                            <span>{err}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {stats.accounts && Object.keys(stats.accounts).length > 0 && (
                      <div className="pl-3 border-l-2 border-slate-800 mt-2 space-y-2">
                        <span className="text-[11px] font-semibold text-slate-500 uppercase">
                          Sub-account breakdown
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                          {Object.entries(stats.accounts).map(([accName, accStats]) => (
                            <div
                              key={accName}
                              className="p-2 rounded bg-slate-900 border border-slate-800/80 text-xs"
                            >
                              <div className="font-semibold text-slate-300 truncate">{accName}</div>
                              <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-400">
                                <span>{accStats.inserted} inserted</span>
                                <span>•</span>
                                <span>{accStats.skipped} skip</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* History Table */}
      <Card>
        <div className="flex items-center justify-between p-5 border-b border-slate-800 bg-slate-950/40">
          <div>
            <h3 className="text-base font-bold text-white">Execution History</h3>
            <p className="text-xs text-slate-400 mt-0.5">Recorded scrape sessions and execution outcomes</p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => loadRuns(page)}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingRuns ? "animate-spin text-emerald-400" : ""}`} />
            <span>Refresh</span>
          </Button>
        </div>

        {runs.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No recorded scrape runs found. Start one above!
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="bg-slate-950/50 border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  <th className="py-3 px-6">Started</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Day Window</th>
                  <th className="py-3 px-6">Configured Sources</th>
                  <th className="py-3 px-6 text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {runs.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                    onClick={() => refreshSelectedRun(run.id)}
                  >
                    <td className="py-4 px-6 whitespace-nowrap">
                      <div className="font-medium text-slate-200">{formatRelativeTime(run.started_at)}</div>
                      <div className="text-[11px] text-slate-500">{formatDate(run.started_at)}</div>
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap">
                      <Badge variant={getStatusBadgeVariant(run.status)}>
                        {run.status}
                      </Badge>
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap text-xs text-slate-300">
                      {run.days} days
                    </td>
                    <td className="py-4 px-6 text-xs text-slate-400 max-w-xs truncate">
                      {run.sources?.join(", ") || "—"}
                    </td>
                    <td className="py-4 px-6 text-right whitespace-nowrap">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          refreshSelectedRun(run.id);
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
        )}
      </Card>
    </div>
  );
}
