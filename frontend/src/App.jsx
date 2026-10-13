import React, { useState, useEffect, useRef } from "react";
import { Briefcase, Play, Database, Sun, Moon, LogOut, Users } from "lucide-react";
import { fetchApi } from "./services/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useActiveRuns } from "./services/queries";
import { getToken, getUser, isAdmin, logout } from "./services/auth";
import JobsExplorer from "./features/jobs/JobsExplorer";
import ScrapeRuns from "./features/scraper/ScrapeRuns";
import LoginPage from "./features/auth/LoginPage";
import UsersPanel from "./features/admin/UsersPanel";

export default function App() {
  const [authed, setAuthed] = useState(() => !!getToken());
  const headerRef = useRef(null);
  const queryClient = useQueryClient();

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />;
  }

  const user = getUser();

  return <AuthedApp headerRef={headerRef} queryClient={queryClient} user={user} />;
}

function AuthedApp({ headerRef, queryClient, user }) {
  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const measure = () => header.parentElement.style.setProperty("--app-header-height", `${header.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  const admin = user?.role === "admin";
  const [currentTab, setCurrentTab] = useState(() => {
    const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
    if (hash === "runs") return "runs";
    if (hash === "users" && user?.role === "admin") return "users";
    return "jobs";
  });
  const countQuery = useQuery({
    queryKey: ["jobs", "count"],
    queryFn: ({ signal }) => fetchApi("jobs/count", { signal }),
    refetchInterval: 5000,
  });
  const totalJobsCount = countQuery.data?.total ?? null;
  const previousCountRef = useRef(null);

  useEffect(() => {
    if (totalJobsCount === null) return;
    if (previousCountRef.current !== null && previousCountRef.current !== totalJobsCount) {
      queryClient.invalidateQueries({ queryKey: ["jobs", "list"] });
      queryClient.invalidateQueries({ queryKey: ["filters"] });
    }
    previousCountRef.current = totalJobsCount;
  }, [totalJobsCount, queryClient]);
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

  const updateRoute = () => {
    const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
    if (hash === "runs") {
      setCurrentTab("runs");
    } else if (hash === "users" && admin) {
      setCurrentTab("users");
    } else {
      setCurrentTab("jobs");
    }
  };

  useEffect(() => {
    updateRoute();
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  const activeQuery = useActiveRuns();
  const activeRuns = activeQuery.data?.items || [];
  const runningCount = activeRuns.filter((run) => ['running', 'stopping'].includes(run.status)).length;
  const queuedCount = activeRuns.filter((run) => run.status === 'queued').length;

  const setTab = (tab) => {
    if (currentTab === "jobs") sessionStorage.setItem("jobs-route", window.location.hash);
    window.location.hash = tab === "jobs" ? (sessionStorage.getItem("jobs-route") || "jobs") : tab;
  };

  return (
    <div className="min-h-screen bg-bg-base flex flex-col font-sans text-text-main selection:bg-accent selection:text-accent-foreground">
      {/* Header */}
      <header ref={headerRef} className="sticky top-0 z-40 bg-bg-surface/95 backdrop-blur-md border-b border-border-subtle shadow-xs">
        <div className="w-full lg:w-[92%] mx-auto px-4 lg:px-8 min-h-16 py-2 flex flex-wrap items-center justify-between gap-2">
          {/* Brand */}
          <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-accent-foreground shadow-xs font-bold">
              <Database className="w-4 h-4" />
            </div>
            <span className="font-semibold text-sm sm:text-base tracking-tight text-text-main hidden md:inline">
              Job Scrapper
            </span>
          </div>

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
                        : "bg-border-subtle text-text-main"
                    }`}
                  >
                    {totalJobsCount.toLocaleString()}
                  </span>
                )}
              </button>

              {admin && <button
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
                {activeRuns.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 tabular-nums"
                    aria-label={`${runningCount} active, ${queuedCount} queued`}
                    title={`${runningCount} active · ${queuedCount} queued`}>
                    <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
                    {activeRuns.length}
                  </span>
                )}
              </button>}

              {admin && (
                <button
                  type="button"
                  aria-current={currentTab === "users" ? "page" : undefined}
                  onClick={() => setTab("users")}
                  className={`flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus ${
                    currentTab === "users"
                      ? "bg-accent text-accent-foreground shadow-xs"
                      : "text-text-muted hover:text-text-main hover:bg-bg-surface"
                  }`}
                >
                  <Users className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  <span className="hidden sm:inline">Users</span>
                </button>
              )}
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

            {/* User & Logout */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-muted hidden sm:inline">{user?.email}</span>
              {user?.role === "admin" && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-accent/15 text-accent">admin</span>
              )}
              <button
                type="button"
                onClick={logout}
                aria-label="Sign out"
                title="Sign out"
                className="p-2 min-h-[44px] min-w-[44px] rounded-xl border border-border-subtle bg-bg-surface hover:bg-bg-surface-elevated text-text-muted hover:text-red-500 transition-all cursor-pointer shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full lg:w-[92%] mx-auto px-4 lg:px-8 py-6">
        {currentTab === "jobs" ? <JobsExplorer /> : currentTab === "users" && admin ? <UsersPanel /> : <ScrapeRuns />}
      </main>

      {/* Footer */}
      <footer className="border-t border-border-subtle py-6 text-center text-xs text-text-dim">
        <div className="w-full lg:w-[92%] mx-auto px-4 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span>Job Scrapper · Machine Learning Training Dataset Pipeline</span>
          <span className="font-mono text-[11px] text-text-dim">
            Local Engine · Fast In-Memory & PostgreSQL Sink
          </span>
        </div>
      </footer>
    </div>
  );
}
