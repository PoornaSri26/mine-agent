import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Bot, Cpu, Loader2, Network, Sparkles } from 'lucide-react';
import { AgentInfo, AgentEvent, AgentsResponse, getAgents } from '../services/geminiService';
import { AgentTrace } from './AgentTrace';

const LAST_RUN_KEY = 'minerakshak:last-run';

interface LastRun {
  question: string;
  confidence: number;
  at: string;
  trace: AgentEvent[];
}

const readLastRun = (): LastRun | null => {
  try {
    const raw = localStorage.getItem(LAST_RUN_KEY);
    return raw ? (JSON.parse(raw) as LastRun) : null;
  } catch {
    return null;
  }
};

export const AgentsScreen: React.FC = () => {
  const [roster, setRoster] = useState<AgentsResponse | null>(null);
  const [lastRun] = useState<LastRun | null>(readLastRun);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAgents()
      .then(setRoster)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load the agent roster.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen pb-24">
      <header className="mb-10 max-w-3xl">
        <p className="mb-3 inline-flex items-center gap-2 rounded border border-[#00E5FF]/20 bg-[#00E5FF]/5 px-3 py-1 font-label text-[10px] uppercase tracking-widest text-[#00E5FF]">
          <Network className="h-3 w-3" /> Supervisor-led team
        </p>
        <h1 className="font-headline text-3xl font-extrabold tracking-tight text-slate-100 sm:text-4xl">Agent Mesh</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-slate-400">
          Each question is handled by six specialised agents sharing one state. The supervisor plans the work, the
          specialists contribute their own evidence, and the critic can send the run back for more research before
          anything reaches you.
        </p>
      </header>

      {loading && (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin text-amber-400" /> Loading the roster…
        </div>
      )}

      {error && (
        <div role="alert" className="mb-6 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {roster && (
        <>
          <section className="mb-10 rounded-2xl border border-white/[0.06] bg-[#111114] p-5 sm:p-7">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-headline text-sm font-semibold uppercase tracking-widest text-slate-400">Run pipeline</h2>
              <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-wider ${roster.llm.enabled ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300' : 'border-amber-500/20 bg-amber-500/5 text-amber-300'}`}>
                <Cpu className="h-3 w-3" />
                {roster.llm.enabled ? `Gemini · ${roster.llm.model}` : 'Deterministic mode · set GOOGLE_API_KEY'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {roster.pipeline.map((stage, index) => (
                <React.Fragment key={stage}>
                  <span className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-200">
                    <span className="mr-2 font-mono text-[10px] text-amber-400">{index + 1}</span>
                    {stage}
                  </span>
                  {index < roster.pipeline.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-slate-600" />}
                </React.Fragment>
              ))}
            </div>
            <p className="mt-4 text-xs leading-relaxed text-slate-500">
              The critic has a conditional edge back to research: if coverage is thin or no page is cited, the team
              repeats the search with broadened queries (up to two passes) instead of returning a guess.
            </p>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {roster.agents.map((agent: AgentInfo, index: number) => (
              <motion.article
                key={agent.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="rounded-2xl border border-white/[0.06] bg-[#111114] p-5"
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bot className="h-4 w-4 text-amber-400" />
                    <h3 className="font-headline text-base font-bold text-slate-100">{agent.name}</h3>
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">stage {agent.stage}</span>
                </div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-500/80">{agent.role}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-slate-400">{agent.description}</p>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {agent.tools.map(tool => (
                    <span key={tool} className="rounded border border-white/[0.07] bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] text-slate-500">
                      {tool}
                    </span>
                  ))}
                </div>
              </motion.article>
            ))}
          </section>

          <section className="mt-10">
            <h2 className="mb-3 flex items-center gap-2 font-headline text-sm font-semibold uppercase tracking-widest text-slate-400">
              <Sparkles className="h-3.5 w-3.5 text-amber-400" /> Last run in this browser
            </h2>
            {lastRun ? (
              <div className="rounded-2xl border border-white/[0.06] bg-[#111114] p-5">
                <p className="text-sm text-slate-200">{lastRun.question}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-slate-600">
                  {new Date(lastRun.at).toLocaleString()}
                </p>
                <AgentTrace events={lastRun.trace} confidence={lastRun.confidence} defaultOpen />
              </div>
            ) : (
              <p className="rounded-2xl border border-white/[0.06] bg-[#111114] p-5 text-sm text-slate-500">
                Run a question in the AI Chatbot tab and its full agent trace will appear here.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
};
