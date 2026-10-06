import React, { useState, useEffect } from "react";
import { Briefcase, Play, Database } from "lucide-react";
import { fetchApi, setSessionToken } from "./services/api";
import JobsExplorer from "./features/jobs/JobsExplorer";
import ScrapeRuns from "./features/scraper/ScrapeRuns";

export default function App() {
  const [currentTab, setCurrentTab] = useState("jobs");
  const [totalJobsCount, setTotalJobsCount] = useState(null);

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
    const hash = window.location.hash.replace("#", "").split("?")[0];
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

  const setTab = (tab) => {
    setCurrentTab(tab);
    window.location.hash = tab;
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col font-sans text-slate-100 selection:bg-emerald-500 selection:text-white">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800">
        <div className="w-full px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white shadow-md shadow-emerald-950 font-bold">
              <Database className="w-4 h-4" />
            </div>
            <span className="font-semibold text-base tracking-tight text-white">
              Job Scrapper
            </span>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1.5 bg-slate-950/70 p-1 rounded-xl border border-slate-800">
            <button
              type="button"
              onClick={() => setTab("jobs")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                currentTab === "jobs"
                  ? "bg-emerald-600 text-white shadow-md shadow-emerald-950"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              <Briefcase className="w-4 h-4" />
              <span>Postings</span>
              {totalJobsCount !== null && (
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                    currentTab === "jobs"
                      ? "bg-emerald-700/80 text-emerald-100"
                      : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {totalJobsCount.toLocaleString()}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setTab("runs")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                currentTab === "runs"
                  ? "bg-emerald-600 text-white shadow-md shadow-emerald-950"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              <Play className="w-4 h-4" />
              <span>Scraper Controller</span>
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full px-4 sm:px-6 lg:px-8 py-6">
        {currentTab === "jobs" ? <JobsExplorer /> : <ScrapeRuns />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        <div className="w-full px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span>Job Scrapper · Machine Learning Training Dataset Pipeline</span>
          <span className="font-mono text-[11px] text-slate-600">
            Local Engine · Fast In-Memory & PostgreSQL Sink
          </span>
        </div>
      </footer>
    </div>
  );
}
