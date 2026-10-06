import React, { useState, useEffect, useRef } from "react";
import { Briefcase, Play, Database, Sun, Moon } from "lucide-react";
import { fetchApi, setSessionToken } from "./services/api";
import JobsExplorer from "./features/jobs/JobsExplorer";
import ScrapeRuns from "./features/scraper/ScrapeRuns";

export default function App() {
  const headerRef = useRef(null);

  useEffect(() => {
    const header = headerRef.current;
    const measure = () => header.parentElement.style.setProperty("--app-header-height", `${header.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  const [currentTab, setCurrentTab] = useState("jobs");
  const [totalJobsCount, setTotalJobsCount] = useState(null);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("app-theme") || "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("app-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const init = async () => {
    try {
      const sess = await fetchApi("session");
      if (sess && sess.token) {
        setSessionToken(sess.token);
      }
      const jobsData = await fetchApi("jobs?page_size=25");
      setTotalJobsCount(jobsData.total || 0);
    } catch (err) {
      console.error("Dashboard initialization error:", err);
    }
  };

  const updateRoute = () => {
    const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
    if (hash === "runs") {
      setCurrentTab("runs");
    } else {
      setCurrentTab("jobs");
    }
  };

  useEffect(() => {
    init();
    updateRoute();
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  const [activeRun, setActiveRun] = useState(null);
  const [now, setNow] = useState(Date.now());

  // Poll active run status for ambient visibility in header
  useEffect(() => {
    let timer = null;
    const checkActiveRuns = async () => {
      try {
        const data = await fetchApi("runs?page=1&page_size=25");
        setActiveRun((data.items || []).find((r) => ["running", "stopping"].includes(r.status)) || null);
        setNow(Date.now());
      } catch {
        // quiet fallback
      }
    };
    checkActiveRuns();
    timer = setInterval(checkActiveRuns, 5000);
    return () => clearInterval(timer);
  }, []);

  const setTab = (tab) => {
    if (currentTab === "jobs") sessionStorage.setItem("jobs-route", window.location.hash);
    window.location.hash = tab === "jobs" ? (sessionStorage.getItem("jobs-route") || "jobs") : "runs";
  };

  return (
    <div className="min-h-screen bg-bg-base flex flex-col font-sans text-text-main selection:bg-accent selection:text-accent-foreground">
      {/* Header */}
      <header ref={headerRef} className="sticky top-0 z-40 bg-bg-surface/95 backdrop-blur-md border-b border-border-subtle shadow-xs">
        <div className="w-full max-w-[1200px] mx-auto px-4 lg:px-8 min-h-16 py-2 flex flex-wrap items-center justify-between gap-2">
          {/* Brand */}
          <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-accent-foreground shadow-xs font-bold">
              <Database className="w-4 h-4" />
            </div>
            <span className="font-semibold text-sm sm:text-base tracking-tight text-text-main hidden md:inline">
              Job Scrapper
            </span>
          </div>

          {/* Ambient Ingestion Status (Visible anywhere in app) */}
          {activeRun && (
            <button
              type="button"
              onClick={() => setTab("runs")}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-status-running-bg border border-status-running-border text-status-running text-xs font-semibold cursor-pointer shrink-0"
              title="Scrape run in progress. Click to view."
            >
              <span className="w-2 h-2 rounded-full bg-status-running animate-ping" />
              <span>{activeRun.status === "stopping" ? "Stopping" : "Scraping"} · {Math.max(0, Math.floor((now - new Date(activeRun.started_at).getTime()) / 60000))}m</span>
            </button>
          )}

          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {/* Navigation Tabs */}
            <nav className="flex items-center gap-1 bg-bg-surface-elevated p-1 rounded-xl border border-border-subtle">
              <button
                type="button"
                aria-label="Job postings"
                aria-current={currentTab === "jobs" ? "page" : undefined}
                onClick={() => setTab("jobs")}
                className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus ${
                  currentTab === "jobs"
                    ? "bg-accent text-accent-foreground shadow-xs"
                    : "text-text-muted hover:text-text-main hover:bg-bg-surface"
                }`}
              >
                <Briefcase className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span className="hidden sm:inline">Postings</span>
                {totalJobsCount !== null && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                      currentTab === "jobs"
                        ? "bg-black/20 text-accent-foreground"
                        : "bg-border-subtle text-text-muted"
                    }`}
                  >
                    {totalJobsCount.toLocaleString()}
                  </span>
                )}
              </button>

              <button
                type="button"
                aria-current={currentTab === "runs" ? "page" : undefined}
                onClick={() => setTab("runs")}
                className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus ${
                  currentTab === "runs"
                    ? "bg-accent text-accent-foreground shadow-xs"
                    : "text-text-muted hover:text-text-main hover:bg-bg-surface"
                }`}
              >
                <Play className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span>Runs</span>
                <span className="hidden md:inline">Controller</span>
              </button>
            </nav>

            {/* Theme Toggle Button */}
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="p-2 min-h-[44px] min-w-[44px] rounded-xl border border-border-subtle bg-bg-surface hover:bg-bg-surface-elevated text-text-muted hover:text-text-main transition-all cursor-pointer shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4 text-amber-400" />
              ) : (
                <Moon className="w-4 h-4 text-text-muted" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-[1200px] mx-auto px-4 lg:px-8 py-6">
        {currentTab === "jobs" ? <JobsExplorer /> : <ScrapeRuns />}
      </main>

      {/* Footer */}
      <footer className="border-t border-border-subtle py-6 text-center text-xs text-text-dim">
        <div className="w-full max-w-[1200px] mx-auto px-4 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span>Job Scrapper · Machine Learning Training Dataset Pipeline</span>
          <span className="font-mono text-[11px] text-text-dim">
            Local Engine · Fast In-Memory & PostgreSQL Sink
          </span>
        </div>
      </footer>
    </div>
  );
}
