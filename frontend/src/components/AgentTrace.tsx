import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, Network, XCircle } from 'lucide-react';
import type { AgentEvent } from '../services/geminiService';

const statusMeta = {
  done: { Icon: CheckCircle2, className: 'text-emerald-400' },
  warn: { Icon: AlertTriangle, className: 'text-amber-400' },
  error: { Icon: XCircle, className: 'text-red-400' },
} as const;

interface AgentTraceProps {
  events?: AgentEvent[] | null;
  confidence?: number;
  defaultOpen?: boolean;
}

/**
 * Renders the supervisor's run: which agents were called, in what order, what
 * each contributed and how long it took. This is the visible proof that the
 * answer came from a collaborating team rather than one prompt.
 */
export const AgentTrace: React.FC<AgentTraceProps> = ({ events, confidence, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);

  if (!events || events.length === 0) return null;

  const totalMs = events.reduce((sum, event) => sum + (event.ms || 0), 0);
  const agents = new Set(events.map(event => event.agent)).size;

  // Steps that finish inside a millisecond are reported as 0ms by the API; show
  // them as "<1ms" and keep the run total in milliseconds while it is under 1s,
  // so a fast run does not read as "0ms" / "0.0s".
  const formatMs = (ms: number) => (ms < 1 ? '<1ms' : `${ms}ms`);
  const formatTotal = (ms: number) => (ms < 1000 ? formatMs(ms) : `${(ms / 1000).toFixed(1)}s`);

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-white/[0.06] bg-[#111114]">
      <button
        type="button"
        onClick={() => setOpen(current => !current)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-white/[0.03]"
      >
        <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <Network className="h-3.5 w-3.5 text-amber-400" />
          Agent mesh · {agents} agents · {events.length} steps
        </span>
        <span className="flex items-center gap-3">
          {typeof confidence === 'number' && (
            <span className="font-mono text-[10px] text-slate-500">confidence {(confidence * 100).toFixed(0)}%</span>
          )}
          <span className="flex items-center gap-1 font-mono text-[10px] text-slate-600">
            <Clock3 className="h-3 w-3" />
            {formatTotal(totalMs)}
          </span>
          <ChevronDown className={`h-4 w-4 text-slate-500 transition ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>

      {open && (
        <ol className="space-y-3 border-t border-white/5 px-4 py-3">
          {events.map((event, index) => {
            const meta = statusMeta[event.status] ?? statusMeta.done;
            const Icon = meta.Icon;
            return (
              <li key={`${event.id}-${index}`} className="flex gap-3">
                <span className="mt-0.5 flex flex-col items-center">
                  <Icon className={`h-3.5 w-3.5 ${meta.className}`} />
                  {index < events.length - 1 && <span className="mt-1 h-full w-px flex-1 bg-white/[0.08]" />}
                </span>
                <div className="min-w-0 pb-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-[13px] font-semibold text-slate-200">{event.name}</span>
                    <span className="text-[10px] uppercase tracking-wider text-slate-600">{event.role}</span>
                    <span className="font-mono text-[10px] text-slate-600">{formatMs(event.ms || 0)}</span>
                  </div>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-slate-400">{event.summary}</p>
                  {event.bullets && event.bullets.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {event.bullets.map((bullet, bulletIndex) => (
                        <li key={bulletIndex} className="text-[11px] leading-relaxed text-slate-500">
                          · {bullet}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};
