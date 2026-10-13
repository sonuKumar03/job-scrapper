import React, { useState } from "react";
import { Database } from "lucide-react";
import { loginApi } from "../../services/api";
import { setToken, setUser } from "../../services/auth";

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await loginApi(email, password);
      setToken(data.access_token);
      setUser(data.user);
      onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-accent flex items-center justify-center text-accent-foreground shadow-xs">
            <Database className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-semibold text-text-main">Job Scrapper</h1>
        </div>

        <form onSubmit={handleSubmit} className="bg-bg-surface border border-border-subtle rounded-xl p-6 shadow-xs space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-text-muted mb-1.5">Email</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border-subtle bg-bg-base text-text-main text-sm focus:outline-none focus:ring-2 focus:ring-border-focus"
              autoComplete="email"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-medium text-text-muted mb-1.5">Password</label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border-subtle bg-bg-base text-text-main text-sm focus:outline-none focus:ring-2 focus:ring-border-focus"
              autoComplete="current-password"
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-accent text-accent-foreground text-sm font-semibold shadow-xs hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
