import { useEffect, useState } from "react";
import LanguagePanel from "@/components/LanguagePanel";
import { getStoredLocale, translate, type Locale } from "@/i18n";
import ElysiaOrb from "@/components/Orb";
import MemoryPanel from "@/components/MemoryPanel";
import PluginPanel from "@/components/PluginPanel";
import PlanPanel from "@/components/PlanPanel";
import AgentPanel from "@/components/AgentPanel";
import DropZone from "@/components/DropZone";
import SyncPanel from "@/components/SyncPanel";
import AdminPanel from "@/components/AdminPanel";
import PreferencesPanel from "@/components/PreferencesPanel";
import { useVoiceAssistant } from "@/hooks/useVoiceAssistant";
import ElsyiaOverlay from "@/components/ElsyiaOverlay";
import SeeSelect from "@/components/SeeSelect";

const isElsyiaOverlay =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("overlay") === "elsyia";

const isSeeSelect =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("overlay") === "see";

export default function App() {
  if (isSeeSelect) {
    return <SeeSelect />;
  }
  if (isElsyiaOverlay) {
    return <ElsyiaOverlay />;
  }
  const { status, toolResult, lastError, startListening, stopListeningAndRespond, forceResetToIdle, isRecording } = useVoiceAssistant();
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [pluginsOpen, setPluginsOpen] = useState(false);
  const [plansOpen, setPlansOpen] = useState(false);
  const [agentsOpen, setAgentsOpen] = useState(false);
  const [syncOpen, setSyncOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [languageOpen, setLanguageOpen] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [locale, setLocale] = useState<Locale>(getStoredLocale());
  const toolPayload = toolResult?.result as
    | { summary?: string; draft?: string; message?: string; matches?: Array<{ path?: string }> }
    | undefined;
  const toolDetail =
    toolPayload?.summary ||
    toolPayload?.draft ||
    toolPayload?.message ||
    (toolPayload?.matches ? `${toolPayload.matches.length} matching local files` : undefined);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (!e.repeat && status === "idle") void startListening();
      }
      if (e.code === "Escape") {
        e.preventDefault();
        if (status !== "idle") void forceResetToIdle();
      }
      if (e.key.toLowerCase() === "m" && !e.repeat) {
        e.preventDefault();
        setMemoryOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "p" && !e.repeat) {
        e.preventDefault();
        setPluginsOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "l" && !e.repeat) {
        e.preventDefault();
        setPlansOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "a" && !e.repeat) {
        e.preventDefault();
        setAgentsOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "s" && !e.repeat) {
        e.preventDefault();
        setSyncOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "e" && !e.repeat) {
        e.preventDefault();
        setAdminOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "i" && !e.repeat) {
        e.preventDefault();
        setLanguageOpen((open) => !open);
      }
      if (e.key.toLowerCase() === "o" && !e.repeat) {
        e.preventDefault();
        setPreferencesOpen((open) => !open);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (isRecording()) void stopListeningAndRespond();
      }
    };
    const onLocaleChange = (event: Event) => {
      const value = (event as CustomEvent<Locale>).detail;
      setLocale(value);
    };
    const onBlur = () => {
      if (isRecording()) void stopListeningAndRespond();
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    window.addEventListener("elysia-locale-change", onLocaleChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("elysia-locale-change", onLocaleChange);
    };
  }, [startListening, stopListeningAndRespond, isRecording, status]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return (
    <div className="w-screen h-screen overflow-hidden bg-void">
      <ElysiaOrb assistantStatus={status} />
      <button
        onClick={() => setLanguageOpen(true)}
        className="fixed left-5 top-5 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "language.select")}
      >
        {locale.toUpperCase()} · I
      </button>
      <LanguagePanel open={languageOpen} onClose={() => setLanguageOpen(false)} />
      <button
        onClick={() => setPreferencesOpen(true)}
        className="fixed left-5 top-28 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label="Open local accessibility and appearance preferences"
      >
        Preferences · O
      </button>
      <PreferencesPanel open={preferencesOpen} onClose={() => setPreferencesOpen(false)} />
      <button
        onClick={() => setMemoryOpen(true)}
        className="fixed right-5 top-5 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openMemory")}
      >
        {translate(locale, "app.memory")}
      </button>
      <MemoryPanel open={memoryOpen} onClose={() => setMemoryOpen(false)} />
      <button
        onClick={() => setPluginsOpen(true)}
        className="fixed right-5 top-16 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openPlugins")}
      >
        {translate(locale, "app.plugins")}
      </button>
      <PluginPanel open={pluginsOpen} onClose={() => setPluginsOpen(false)} />
      <button
        onClick={() => setPlansOpen(true)}
        className="fixed right-5 top-28 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openPlans")}
      >
        {translate(locale, "app.plans")}
      </button>
      <PlanPanel open={plansOpen} onClose={() => setPlansOpen(false)} />
      <button
        onClick={() => setAgentsOpen(true)}
        className="fixed right-5 top-40 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openAgents")}
      >
        {translate(locale, "app.agents")}
      </button>
      <AgentPanel open={agentsOpen} onClose={() => setAgentsOpen(false)} />
      <button
        onClick={() => setSyncOpen(true)}
        className="fixed right-5 top-52 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openSync")}
      >
        {translate(locale, "app.sync")}
      </button>
      <SyncPanel open={syncOpen} onClose={() => setSyncOpen(false)} />
      <button
        onClick={() => setAdminOpen(true)}
        className="fixed right-5 top-64 z-10 rounded-xl border border-cyan-200/15 bg-slate-950/60 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-cyan-100/80 backdrop-blur hover:bg-cyan-300/10"
        aria-label={translate(locale, "app.openAdmin")}
      >
        {translate(locale, "app.admin")}
      </button>
      <AdminPanel open={adminOpen} onClose={() => setAdminOpen(false)} />
      <DropZone />
      {toolResult && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 text-xs text-cyan-100 bg-black/60 px-3 py-2 rounded-lg backdrop-blur border border-cyan-300/20">
          {toolResult.confirmation_required
            ? toolResult.confirmation_message || translate(locale, "app.confirmationRequired")
            : toolResult.status === "completed"
              ? toolDetail || translate(locale, "app.completed", { tool: toolResult.tool_name })
              : toolResult.error || translate(locale, "app.actionFailed")}
        </div>
      )}
      {lastError && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 text-xs text-red-300 bg-black/50 px-3 py-2 rounded-lg backdrop-blur">
          {lastError}
        </div>
      )}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 text-[11px] tracking-widest opacity-40">
        {translate(locale, "app.hint")} · I FOR LANGUAGE · O FOR PREFERENCES
      </div>
    </div>
  );
}
