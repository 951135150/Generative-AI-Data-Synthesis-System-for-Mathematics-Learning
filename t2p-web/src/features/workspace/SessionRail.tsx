'use client';

import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  Circle,
  Clock3,
  FlaskConical,
  Gauge,
  Layers3,
  Lightbulb,
} from 'lucide-react';

import type { AuditResult, Problem } from './types';

interface SessionRailProps {
  problems: Problem[];
  activeIndex: number;
  activeProblem?: Problem;
  result?: AuditResult;
  generating: boolean;
  auditing: boolean;
  onSelectProblem: (index: number) => void;
  onOpenAgents: () => void;
}

export function SessionRail({
  problems,
  activeIndex,
  activeProblem,
  result,
  generating,
  auditing,
  onSelectProblem,
  onOpenAgents,
}: SessionRailProps) {
  const statusLabel = generating
    ? 'Generating exercise'
    : auditing
      ? 'Reviewing reasoning'
      : 'Workspace ready';

  return (
    <aside className="workspace-rail session-rail" aria-label="Session context">
      <div className="rail-heading compact">
        <span>03</span>
        <div>
          <p>Research session</p>
          <h2>Context &amp; status</h2>
        </div>
      </div>

      <section className="session-status-card" aria-live="polite">
        <div className={`session-status-icon ${generating || auditing ? 'is-busy' : ''}`}>
          <Activity size={17} />
        </div>
        <div>
          <small>Current state</small>
          <strong>{statusLabel}</strong>
        </div>
        <span className={generating || auditing ? 'status-dot is-busy' : 'status-dot'} />
      </section>

      <section className="session-metrics" aria-label="Current problem summary">
        <div>
          <Layers3 size={15} />
          <span><small>Folio</small><strong>{problems.length} problems</strong></span>
        </div>
        <div>
          <Gauge size={15} />
          <span><small>Difficulty</small><strong>Level {activeProblem?.difficulty || '—'}</strong></span>
        </div>
        <div>
          <Clock3 size={15} />
          <span><small>AI operation</small><strong>1–2 minutes</strong></span>
        </div>
      </section>

      {result ? (
        <section className={`session-review-summary ${result.is_correct ? 'is-passed' : 'is-revise'}`}>
          <div className="session-section-title">
            <CheckCircle2 size={15} /> Mentor review
          </div>
          <div className="session-score">
            <strong>{result.logic_alignment_score}</strong><span>/100</span>
          </div>
          <p>{result.is_correct ? 'Reasoning accepted' : 'Revision recommended'}</p>
          {result.next_hint && (
            <div className="session-hint"><Lightbulb size={13} /> {result.next_hint}</div>
          )}
        </section>
      ) : (
        <section className="session-review-summary is-empty">
          <div className="session-section-title"><Circle size={14} /> Mentor review</div>
          <p>Submit an answer to reveal logical alignment and individualized guidance.</p>
        </section>
      )}

      <section className="folio-index">
        <div className="session-section-title">Problem folio</div>
        {problems.length > 0 ? (
          <div className="folio-index-list">
            {problems.map((problem, index) => (
              <button
                type="button"
                key={`${problem.id}-${index}`}
                onClick={() => onSelectProblem(index)}
                className={activeIndex === index ? 'is-active' : ''}
                aria-current={activeIndex === index ? 'true' : undefined}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>
                <span><strong>{problem.topic}</strong><small>{problem.sub_topic || 'Core concept'}</small></span>
              </button>
            ))}
          </div>
        ) : (
          <p className="folio-empty">No exercises generated in this session.</p>
        )}
      </section>

      <button type="button" className="agent-lab-entry" onClick={onOpenAgents}>
        <span><FlaskConical size={16} /><strong>Agent Laboratory</strong></span>
        <small>Observe collaborative synthesis</small>
      </button>

      <div className="session-runtime">
        <BrainCircuit size={14} />
        <span><small>Inference model</small><strong>DeepSeek V4 Pro</strong></span>
      </div>
    </aside>
  );
}
