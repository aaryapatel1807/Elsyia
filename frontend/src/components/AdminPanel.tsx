import { useCallback, useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8000/api/v1";
type Workspace = { id: string; name: string; created_at: string; updated_at: string };
type Member = { id: string; display_name: string; role: string; status: string };
type Policy = { key: string; enabled: boolean; updated_at: string };
type Status = { enabled: boolean; workspace: Workspace; member_count: number; analytics_opt_in: boolean; admin_auth_configured: boolean };
type Analytics = { enabled: boolean; events: Array<{ event: string; count: number; last_at: string }> };
type IdentityStatus = { sso_enabled: boolean; sso_configured: boolean; mfa_readiness_enabled: boolean };
type Invitation = { id: string; display_name: string; role: string; status: string; expires_at: string; invitation_token?: string };

function bearerHeaders(sessionToken: string): Record<string, string> {
  return sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {};
}

export default function AdminPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [identity, setIdentity] = useState<IdentityStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [sessionExpiresAt, setSessionExpiresAt] = useState("");
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [lastInviteToken, setLastInviteToken] = useState("");

  const load = useCallback(async (token = sessionToken) => {
    if (!token) {
      setMessage("Enter the local admin token and connect to create a short-lived session.");
      return;
    }
    try {
      const request = (path: string) => fetch(`${API_BASE}${path}`, { headers: bearerHeaders(token) });
      const responses = await Promise.all([
        request("/admin/status"),
        request("/admin/members"),
        request("/admin/policies"),
        request("/admin/analytics"),
        request("/admin/invitations"),
      ]);
      if (responses.some((response) => !response.ok)) throw new Error("Session expired or administration is unavailable");
      const [statusData, membersData, policiesData, analyticsData, invitationsData] = await Promise.all(responses.map((response) => response.json()));
      setStatus(statusData as Status);
      setMembers((membersData as { members: Member[] }).members);
      setPolicies((policiesData as { policies: Policy[] }).policies);
      setAnalytics(analyticsData as Analytics);
      setInvitations(invitationsData as Invitation[]);
      const identityResponse = await fetch(`${API_BASE}/admin/auth/status`);
      if (identityResponse.ok) setIdentity((await identityResponse.json()) as IdentityStatus);
      setMessage(null);
    } catch (error) {
      setSessionToken("");
      setMessage(error instanceof Error ? error.message : "Administration unavailable.");
    }
  }, [sessionToken]);

  useEffect(() => {
    if (open) setMessage(null);
  }, [open]);

  const connect = async () => {
    if (!adminToken) {
      setMessage("Enter the local admin token to create a session.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/admin/auth/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_token: adminToken }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Session creation failed.");
      setSessionToken(data.session_token as string);
      setSessionExpiresAt(data.expires_at as string);
      setAdminToken("");
      await load(data.session_token as string);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Session creation failed.");
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    if (sessionToken) await fetch(`${API_BASE}/admin/auth/logout`, { method: "POST", headers: bearerHeaders(sessionToken) }).catch(() => undefined);
    setSessionToken("");
    setSessionExpiresAt("");
    setStatus(null);
    setMembers([]);
    setPolicies([]);
    setAnalytics(null);
    setMessage("Session ended.");
  };

  const togglePolicy = async (policy: Policy) => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/admin/policies`, {
        method: "POST",
        headers: { ...bearerHeaders(sessionToken), "Content-Type": "application/json" },
        body: JSON.stringify({ key: policy.key, enabled: !policy.enabled }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Policy update failed.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Policy update failed.");
    } finally {
      setBusy(false);
    }
  };

  const createInvitation = async () => {
    if (!inviteName.trim()) {
      setMessage("Enter a display name for the invitation.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/admin/invitations`, {
        method: "POST",
        headers: { ...bearerHeaders(sessionToken), "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: inviteName, role: inviteRole, ttl_hours: 72 }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Invitation creation failed.");
      setInviteName("");
      setLastInviteToken(data.invitation_token as string);
      setMessage("Copy the one-time invitation token now; it is not shown again.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Invitation creation failed.");
    } finally {
      setBusy(false);
    }
  };

  const prepareMfa = async () => {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/admin/auth/mfa/enroll`, { method: "POST", headers: bearerHeaders(sessionToken) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "MFA enrollment could not be prepared.");
      setMessage(`MFA readiness record created: ${data.status}. Provider setup is still required.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "MFA enrollment could not be prepared.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-[min(94vw,30rem)] max-w-[30rem] overflow-y-auto border-l border-cyan-200/15 bg-slate-950/95 p-5 text-cyan-50 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-cyan-100/60">Phase 12</p>
          <h2 className="mt-1 text-lg font-light tracking-wide">Enterprise Admin</h2>
        </div>
        <button type="button" onClick={onClose} className="text-sm text-cyan-100/60 hover:text-cyan-50">Close</button>
      </div>

      {!sessionToken ? (
        <div className="mt-4 rounded-lg border border-cyan-200/10 bg-slate-900/70 p-3">
          <label className="text-[10px] uppercase tracking-[0.16em] text-cyan-100/55" htmlFor="admin-token">Local bootstrap token</label>
          <div className="mt-2 flex gap-2">
            <input id="admin-token" type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} placeholder="Used once, not stored" className="min-w-0 flex-1 rounded-lg border border-cyan-200/15 bg-black/30 px-2 py-2 text-xs text-cyan-50 outline-none" />
            <button type="button" onClick={() => void connect()} disabled={busy} className="rounded-lg border border-cyan-200/15 px-2 py-2 text-[10px] uppercase tracking-[0.1em] text-cyan-100/70 hover:bg-cyan-300/10 disabled:opacity-40">Connect</button>
          </div>
          <p className="mt-2 text-[10px] text-cyan-100/40">A short-lived bearer session is kept only in memory.</p>
        </div>
      ) : (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-emerald-200/15 bg-emerald-950/20 p-3 text-xs">
          <span className="text-emerald-100/80">Session active until {sessionExpiresAt ? new Date(sessionExpiresAt).toLocaleTimeString() : "expiry"}</span>
          <button type="button" onClick={() => void signOut()} className="text-emerald-100/60 hover:text-emerald-50">Sign out</button>
        </div>
      )}
      {message && <p className="mt-3 rounded-lg border border-amber-200/20 bg-amber-950/20 p-3 text-xs text-amber-100/80">{message}</p>}

      {status && (
        <div className="mt-5 rounded-xl border border-cyan-200/10 bg-cyan-950/20 p-3 text-xs text-cyan-100/75">
          <p>Workspace: <span className="text-cyan-50">{status.workspace.name}</span></p>
          <p className="mt-1">Members: <span className="text-cyan-50">{status.member_count}</span></p>
          <p className="mt-1">Analytics: <span className="text-amber-100">{status.analytics_opt_in ? "opted in" : "disabled"}</span></p>
          <p className="mt-1">SSO: <span className="text-amber-100">{identity?.sso_enabled ? "configured/adapter pending" : "disabled"}</span></p>
        </div>
      )}

      {sessionToken && <>
        <section className="mt-5">
          <div className="flex items-center justify-between"><h3 className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">Policies</h3><button type="button" onClick={() => void prepareMfa()} disabled={busy} className="text-[10px] uppercase tracking-[0.1em] text-cyan-100/60 hover:text-cyan-50">Prepare MFA</button></div>
          <div className="mt-2 space-y-2">
            {policies.map((policy) => (
              <button key={policy.key} type="button" onClick={() => void togglePolicy(policy)} disabled={busy} className="flex w-full items-center justify-between rounded-lg border border-cyan-200/10 bg-slate-900/70 px-3 py-2 text-left text-xs hover:bg-cyan-300/10 disabled:opacity-40">
                <span className="truncate pr-3">{policy.key}</span>
                <span className={policy.enabled ? "text-emerald-200" : "text-cyan-100/40"}>{policy.enabled ? "ON" : "OFF"}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="mt-5">
          <h3 className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">Members</h3>
          <div className="mt-2 space-y-2">
            {members.map((member) => <div key={member.id} className="flex items-center justify-between rounded-lg border border-cyan-200/10 bg-slate-900/70 px-3 py-2 text-xs"><span>{member.display_name}</span><span className="text-cyan-100/45">{member.role} · {member.status}</span></div>)}
          </div>
        </section>

        <section className="mt-5">
          <h3 className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">Invitations</h3>
          <div className="mt-2 flex gap-2">
            <input value={inviteName} onChange={(event) => setInviteName(event.target.value)} placeholder="Display name" className="min-w-0 flex-1 rounded-lg border border-cyan-200/15 bg-black/30 px-2 py-2 text-xs text-cyan-50 outline-none" />
            <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)} className="rounded-lg border border-cyan-200/15 bg-slate-900 px-2 py-2 text-xs text-cyan-50"><option value="member">member</option><option value="viewer">viewer</option><option value="admin">admin</option></select>
            <button type="button" onClick={() => void createInvitation()} disabled={busy} className="rounded-lg border border-cyan-200/15 px-2 py-2 text-[10px] uppercase tracking-[0.1em] text-cyan-100/70 disabled:opacity-40">Invite</button>
          </div>
          {lastInviteToken && <p className="mt-2 break-all rounded-lg border border-amber-200/20 bg-amber-950/20 p-2 text-[10px] text-amber-100/80">One-time token: {lastInviteToken}</p>}
          <div className="mt-2 space-y-1">{invitations.map((invitation) => <p key={invitation.id} className="text-xs text-cyan-100/55">{invitation.display_name} · {invitation.role} · {invitation.status} · expires {new Date(invitation.expires_at).toLocaleDateString()}</p>)}</div>
        </section>

        <section className="mt-5">
          <h3 className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">Analytics</h3>
          <p className="mt-2 text-xs text-cyan-100/55">{analytics?.enabled ? "Local opt-in counters only; no content is collected." : "Disabled by policy."}</p>
          {analytics?.enabled && analytics.events.map((event) => <p key={event.event} className="mt-1 text-xs text-cyan-100/65">{event.event}: {event.count}</p>)}
        </section>
      </>}
    </aside>
  );
}
