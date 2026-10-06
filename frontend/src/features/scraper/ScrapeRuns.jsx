import React, { useState, useEffect } from "react";
import {
  Play,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession, useRuns, useActiveRuns } from "../../services/queries";
import { fetchApi } from "../../services/api";
import { formatDate, formatRelativeTime } from "../../utils/date";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";

export default function ScrapeRuns() {
  const queryClient = useQueryClient();
  const sessionQuery = useSession();
  const availableSources = sessionQuery.data?.sources || [];
  const [selectedSources, setSelectedSources] = useState([]);
  const [days, setDays] = useState(1);

  const [page, setPage] = useState(1);

  const runsQuery = useRuns(page);
  const activeQuery = useActiveRuns();
  const activeRuns = activeQuery.data?.items || [];
  const capacity = activeQuery.data?.capacity;
  const queueFull = capacity && activeRuns.length >= capacity.queued;
  const runs = runsQuery.data?.items || [];
  const loadingRuns = runsQuery.isFetching;
  const [selectedRunId, setSelectedRunId] = useState(null);
  const detailQuery = useQuery({
    queryKey: ["runs", "detail", selectedRunId],
    queryFn: ({ signal }) => fetchApi(`runs/${selectedRunId}`, { signal }),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => ["queued", "running", "stopping"].includes(query.state.data?.status) ? 2000 : false,
  });
  const selectedRun = selectedRunId ? detailQuery.data : null;
  const invalidateScrapeData = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["runs"] }),
    queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    queryClient.invalidateQueries({ queryKey: ["filters"] }),
  ]);
  const startMutation = useMutation({
    mutationFn: (data) => fetchApi("runs", { method: "POST", body: JSON.stringify(data) }),
    onSuccess: invalidateScrapeData,
  });
  const stopMutation = useMutation({
    mutationFn: (id) => fetchApi(`runs/${id}/stop`, { method: "POST", body: "{}" }),
    onSuccess: invalidateScrapeData,
  });
  const isSubmitting = startMutation.isPending;
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  const loadRuns = async (targetPage = page) => {
    setPage(targetPage);
    await queryClient.invalidateQueries({ queryKey: ["runs", targetPage] });
  };
  const refreshSelectedRun = (runId) => {
    setSelectedRunId(runId);
    return queryClient.invalidateQueries({ queryKey: ["runs", "detail", runId] });
  };
  useEffect(() => {
    if (sessionQuery.data?.sources.length) setSelectedSources([sessionQuery.data.sources[0]]);
  }, [sessionQuery.data]);
  useEffect(() => {
    if (runsQuery.isError || detailQuery.isError || sessionQuery.isError || activeQuery.isError) {
      setStatusMessage("Could not load scraper data. Refresh to try again.");
      setStatusError(true);
    }
  }, [runsQuery.isError, detailQuery.isError, sessionQuery.isError, activeQuery.isError]);

  const startScrape = async () => {
    if (selectedSources.length === 0) {
      setStatusMessage("Select at least one source connector.");
      setStatusError(true);
      return;
    }

    if (!Number.isInteger(Number(days)) || Number(days) < 1 || Number(days) > 365) {
      setStatusMessage("Enter a whole day window from 1 to 365."); setStatusError(true); return;
    }
    setReviewing(false);
    setStatusMessage("Dispatching scrape task...");
    setStatusError(false);

    try {
      const res = await startMutation.mutateAsync({ sources: selectedSources, days: Number(days) });

      setStatusMessage("Scrape queued. It will start when a slot is available.");
      setStatusError(false);

      await loadRuns(1);
      if (res.id) {
        await refreshSelectedRun(res.id);
      }
    } catch (err) {
      setStatusMessage(err.message || "Could not start scraping. Check the local API and try again.");
      setStatusError(true);
    }
  };

  const toggleSource = (source) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const stopScrape = async (runId) => {
    try {
      const res = await stopMutation.mutateAsync(runId);
      setStatusMessage(res.status === 'stopped' ? 'Queued scrape stopped.' : "Stop requested. The current batch will finish saving before the scrape stops.");
      setStatusError(false);
    } catch (err) {
      setStatusMessage(err.message || "Could not request a stop. Try again.");
      setStatusError(true);
    }
  };

  const getStatusBadgeVariant = (status) => {
    if (status === "completed") return "success";
    if (status === "running") return "running";
    if (["queued", "pending", "stopping", "stopped", "partial", "interrupted"].includes(status)) return "warning";
    return "error";
  };

  return (
    <div className="space-y-8">
      {activeRuns.length > 0 && <Card className="p-5 space-y-4" role="region" aria-label="Active scrapes">
        <h2 className="font-semibold">Active scrapes{capacity ? ` · ${capacity.active} execution slots` : ''}</h2>
        <div className="divide-y divide-border-subtle">
          {activeRuns.map((run) => <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{run.sources.join(', ')}</span><Badge variant={getStatusBadgeVariant(run.status)}>{run.status}</Badge></div>
              <p className="text-sm text-text-muted">{run.days}-day window · {run.started_at ? `Started ${formatRelativeTime(run.started_at)}` : `Queued ${formatRelativeTime(run.queued_at)}`}</p>
              <p className="text-xs text-text-dim font-mono break-all">{run.id}</p>
              {run.dispatch_error && <p className="text-sm text-text-muted">Waiting for task delivery. The dispatcher will retry automatically.</p>}
              {stopMutation.isError && stopMutation.variables === run.id && <p role="alert" className="text-sm text-status-danger">{stopMutation.error.message}</p>}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => refreshSelectedRun(run.id)}>Details</Button>
              <Button variant="danger" loading={stopMutation.isPending && stopMutation.variables === run.id}
                disabled={run.status === 'stopping' || (stopMutation.isPending && stopMutation.variables === run.id)}
                aria-label={`Stop scrape ${run.id}`} onClick={() => stopScrape(run.id)}>
                {run.status === 'stopping' ? 'Stopping…' : run.status === 'queued' ? 'Stop queued run' : 'Stop scrape'}
              </Button>
            </div>
          </div>)}
        </div>
        <p className="text-sm text-text-muted">Stopping keeps saved jobs. Each run can be stopped independently.</p>
      </Card>}
      {/* Trigger Scrape Card */}
      <Card className="p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle">
          <div>
            <h2 className="text-lg font-bold text-text-main flex items-center gap-2">
              <Play className="w-5 h-5 text-accent" />
              Trigger Scrape Run
            </h2>
            <p className="text-xs text-text-muted mt-1">
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
          <div className="text-xs font-semibold uppercase tracking-wider text-text-muted block">
            Available Connectors ({selectedSources.length}/{availableSources.length} selected)
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
            {availableSources.map((source) => {
              const isSelected = selectedSources.includes(source);
              return (
                <button
                  key={source}
                  type="button"
                  role="button"
                  aria-pressed={isSelected}
                  onClick={() => { setReviewing(false); toggleSource(source); }}
                  className={`flex items-center justify-between px-3 py-2.5 min-h-[44px] rounded-xl text-xs font-medium border transition-all text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-1 ${
                    isSelected
                      ? "bg-accent-subtle border-accent text-accent font-semibold shadow-xs"
                      : "bg-bg-surface-elevated border-border-subtle text-text-muted hover:bg-bg-surface hover:text-text-main"
                  }`}
                >
                  <span className="min-w-0">{source}<span className="block text-text-muted font-normal mt-1">{["greenhouse", "lever", "ashby", "workday", "workable"].includes(source) ? "ATS · all open jobs" : "Board · date window"}</span></span>
                  {isSelected && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-accent shrink-0 ml-1.5" />
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
                className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-1.5"
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
                className="w-28 px-3 py-2 bg-bg-surface border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus font-mono"
              />
            </div>
            <div className="text-[11px] text-text-dim max-w-xs pt-4">
              General job boards filter postings created in the last {days} {days == 1 ? "day" : "days"}.
            </div>
          </div>

          <div className="flex items-center gap-3">
            {statusMessage && (
              <span
                role="status"
                className={`text-xs font-medium ${
                  statusError ? "text-status-danger" : "text-status-success"
                }`}
              >
                {statusMessage}
              </span>
            )}
            <Button
              variant="primary"
              size="lg"
              loading={isSubmitting}
              disabled={!sessionQuery.data || isSubmitting || queueFull || selectedSources.length === 0}
              onClick={() => setReviewing(true)}
            >
              <Play className="w-4 h-4 fill-current" />
              <span>{queueFull ? "Queue full" : "Start Scrape"}</span>
            </Button>
          </div>
        </div>
      </Card>

      {reviewing && <Card className="p-5 space-y-3" role="region" aria-label="Review scrape run">
        <h3 className="font-semibold">Review scrape run</h3>
        <p className="text-sm text-text-muted">Sources: {selectedSources.join(", ")}. General boards use a {days}-day window; company ATS feeds collect all open jobs. Requests use the existing pacing limits.</p>
        <div className="flex flex-wrap gap-3"><Button variant="primary" disabled={queueFull || isSubmitting || !selectedSources.length} onClick={startScrape}>Confirm and start</Button><Button onClick={() => setReviewing(false)}>Cancel</Button></div>
      </Card>}
      {/* Selected Run Details */}
      {selectedRun && (
        <Card className="p-6 space-y-6">
          <div className="flex items-start justify-between pb-4 border-b border-border-subtle">
            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-base font-bold text-text-main">Execution Inspector</h3>
                <Badge variant={getStatusBadgeVariant(selectedRun.status)}>
                  {selectedRun.status}
                </Badge>
              </div>
              <p className="text-xs text-text-dim font-mono mt-1">ID: {selectedRun.id}</p>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSelectedRunId(null)}
            >
              Close Detail
            </Button>
          </div>

          {selectedRun.error_message && <p role="status" className="text-sm text-text-muted">{selectedRun.error_message}</p>}
          {selectedRun.dispatch_error && <p role="status" className="text-sm text-text-muted">Task delivery is delayed. This run remains queued and will retry automatically.</p>}
          {/* Stats Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 bg-bg-surface-elevated rounded-xl border border-border-subtle">
              <span className="text-[11px] text-text-dim uppercase font-semibold">Started</span>
              <div className="text-xs font-medium text-text-main mt-0.5">
                {formatDate(selectedRun.started_at)}
              </div>
            </div>
            <div className="p-3 bg-bg-surface-elevated rounded-xl border border-border-subtle">
              <span className="text-[11px] text-text-dim uppercase font-semibold">Finished</span>
              <div className="text-xs font-medium text-text-main mt-0.5">
                {formatDate(selectedRun.finished_at)}
              </div>
            </div>
            <div className="p-3 bg-bg-surface-elevated rounded-xl border border-border-subtle">
              <span className="text-[11px] text-text-dim uppercase font-semibold">Days Cutoff</span>
              <div className="text-xs font-medium text-text-main mt-0.5">
                {selectedRun.days} days
              </div>
            </div>
            <div className="p-3 bg-bg-surface-elevated rounded-xl border border-border-subtle">
              <span className="text-[11px] text-text-dim uppercase font-semibold">Sources</span>
              <div className="text-xs font-medium text-text-main mt-0.5 truncate">
                {selectedRun.sources?.join(", ")}
              </div>
            </div>
          </div>

          {/* Connectors breakdown */}
          {selectedRun.results && Object.keys(selectedRun.results).length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                Connector Execution Results
              </h4>
              <div className="space-y-3">
                {Object.entries(selectedRun.results).map(([sourceName, stats]) => (
                  <div
                    key={sourceName}
                    className="p-4 rounded-xl bg-bg-surface-elevated border border-border-subtle space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-text-main">{sourceName}</span>
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
                        <div className="text-xs text-text-muted flex items-center gap-3">
                          <span className="text-text-main font-semibold">
                            {stats.found.toLocaleString()} found
                          </span>
                          <span className="text-accent font-semibold">
                            {(stats.inserted ?? 0).toLocaleString()} inserted
                          </span>
                          <span className="text-text-dim">
                            {(stats.skipped ?? 0).toLocaleString()} skipped
                          </span>
                        </div>
                      )}
                    </div>

                    {stats.errors && stats.errors.length > 0 && (
                      <div className="p-2.5 rounded bg-status-danger-bg border border-status-danger-border text-xs text-status-danger space-y-1">
                        {stats.errors.map((err, i) => (
                          <div key={i} className="flex items-start gap-1.5">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                            <span>{err}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {stats.accounts && Object.keys(stats.accounts).length > 0 && (
                      <div className="pl-3 border-l-2 border-border-subtle mt-2 space-y-2">
                        <span className="text-[11px] font-semibold text-text-dim uppercase">
                          Sub-account breakdown
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                          {Object.entries(stats.accounts).map(([accName, accStats]) => (
                            <div
                              key={accName}
                              className="p-2 rounded bg-bg-surface border border-border-subtle text-xs"
                            >
                              <div className="font-semibold text-text-main truncate">{accName}</div>
                              <div className="flex items-center gap-2 mt-1 text-[11px] text-text-muted">
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
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between p-5 border-b border-border-subtle bg-bg-surface-elevated/40">
          <div>
            <h3 className="text-base font-bold text-text-main">Execution History</h3>
            <p className="text-xs text-text-muted mt-0.5">Recorded scrape sessions and execution outcomes</p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => loadRuns(page)}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingRuns ? "animate-spin text-accent" : ""}`} />
            <span>Refresh</span>
          </Button>
        </div>

        {runs.length === 0 ? (
          <div className="p-12 text-center text-text-dim text-sm">
            No recorded scrape runs found. Start one above!
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="bg-bg-surface-elevated border-b border-border-subtle text-xs font-semibold uppercase tracking-wider text-text-muted">
                  <th className="py-3 px-6">Started</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Day Window</th>
                  <th className="py-3 px-6">Configured Sources</th>
                  <th className="py-3 px-6 text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {runs.map((run) => (
                  <tr
                    key={run.id}
                    tabIndex={0}
                    role="button"
                    aria-label={`Inspect run ${run.id}`}
                    className="hover:bg-bg-surface-elevated/80 transition-colors group cursor-pointer focus-visible:outline-none focus-visible:bg-bg-surface-elevated focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-inset"
                    onClick={() => refreshSelectedRun(run.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        refreshSelectedRun(run.id);
                      }
                    }}
                  >
                    <td className="py-4 px-6 whitespace-nowrap">
                      <div className="font-medium text-text-main">{formatRelativeTime(run.started_at || run.queued_at)}</div>
                      <div className="text-[11px] text-text-dim">{run.started_at ? 'Started' : 'Queued'} {formatDate(run.started_at || run.queued_at)}</div>
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap">
                      <Badge variant={getStatusBadgeVariant(run.status)}>
                        {run.status}
                      </Badge>
                    </td>
                    <td className="py-4 px-4 whitespace-nowrap text-xs text-text-muted">
                      {run.days} days
                    </td>
                    <td className="py-4 px-6 text-xs text-text-muted max-w-xs truncate">
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
