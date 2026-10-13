import React, { useState } from "react";
import { UserPlus, Shield, User } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchApi } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";

export default function UsersPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("normal");
  const [error, setError] = useState("");

  const usersQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: ({ signal }) => fetchApi("admin/users", { signal }),
  });

  const createMutation = useMutation({
    mutationFn: (data) => fetchApi("admin/users", { method: "POST", body: JSON.stringify(data) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      setShowForm(false);
      setEmail("");
      setPassword("");
      setRole("normal");
      setError("");
    },
    onError: (err) => setError(err.message),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    createMutation.mutate({ email, password, role });
  };

  const users = usersQuery.data || [];

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-main flex items-center gap-2">
            <Shield className="w-5 h-5 text-accent" />
            User Management
          </h2>
          <p className="text-xs text-text-muted mt-1">Invite and manage user accounts</p>
        </div>
        {!showForm && (
          <Button variant="primary" size="md" onClick={() => setShowForm(true)}>
            <UserPlus className="w-4 h-4" />
            <span>Invite User</span>
          </Button>
        )}
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <h3 className="text-sm font-semibold text-text-main">New User</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="invite-email" className="block text-xs font-medium text-text-muted mb-1.5">Email</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="off"
                  className="w-full px-3 py-2 rounded-lg border border-border-subtle bg-bg-base text-text-main text-sm focus:outline-none focus:ring-2 focus:ring-border-focus"
                />
              </div>
              <div>
                <label htmlFor="invite-password" className="block text-xs font-medium text-text-muted mb-1.5">Password</label>
                <input
                  id="invite-password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full px-3 py-2 rounded-lg border border-border-subtle bg-bg-base text-text-main text-sm focus:outline-none focus:ring-2 focus:ring-border-focus"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1.5">Role</label>
              <div className="flex gap-3">
                {["normal", "admin"].map((r) => (
                  <label key={r} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs cursor-pointer ${role === r ? "bg-accent-subtle border-accent text-accent font-semibold" : "bg-bg-surface border-border-subtle text-text-main hover:bg-bg-surface-elevated"}`}>
                    <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} className="accent-accent" />
                    {r === "admin" ? <Shield className="w-3.5 h-3.5" /> : <User className="w-3.5 h-3.5" />}
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </label>
                ))}
              </div>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
            <div className="flex gap-2 pt-2">
              <Button variant="primary" type="submit" loading={createMutation.isPending}>
                Create User
              </Button>
              <Button variant="secondary" onClick={() => { setShowForm(false); setError(""); }}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="p-5 border-b border-border-subtle bg-bg-surface-elevated/40">
          <h3 className="text-base font-bold text-text-main">Users</h3>
          <p className="text-xs text-text-muted mt-0.5">{users.length} account{users.length !== 1 ? "s" : ""}</p>
        </div>
        {usersQuery.isPending ? (
          <div className="p-8 text-center text-text-muted text-sm">Loading…</div>
        ) : users.length === 0 ? (
          <div className="p-8 text-center text-text-dim text-sm">No users yet.</div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {users.map((u) => (
              <div key={u.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${u.role === "admin" ? "bg-accent/15 text-accent" : "bg-bg-surface-elevated text-text-muted"}`}>
                    {u.email.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-main truncate">{u.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={u.role === "admin" ? "warning" : "default"}>
                    {u.role}
                  </Badge>
                  {!u.is_active && <Badge variant="error">disabled</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
