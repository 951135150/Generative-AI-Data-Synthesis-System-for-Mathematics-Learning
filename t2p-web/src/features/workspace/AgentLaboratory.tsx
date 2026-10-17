'use client';

import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Database,
  FlaskConical,
  Loader2,
  MessageSquareText,
  Play,
  Sparkles,
  Square,
} from 'lucide-react';

import type { AgentMessage, SynthesisResult } from './types';

interface AgentLaboratoryProps {
  topics: string[];
  selectedTopics: string[];
  count: number;
  difficulty: number;
  mode: string;
  questionType: string;
  running: boolean;
  messages: AgentMessage[];
  result: SynthesisResult | null;
  error: string | null;
  onToggleTopic: (topic: string) => void;
  onCountChange: (value: number) => void;
  onDifficultyChange: (value: number) => void;
  onModeChange: (value: string) => void;
  onQuestionTypeChange: (value: string) => void;
  onStart: () => void;
  onStop: () => void;
  onOpenStudio: () => void;
}

const MESSAGE_COLORS: Record<string, string> = {
  request: 'is-request',
  response: 'is-response',
  approve: 'is-approve',
  reject: 'is-reject',
  delegate: 'is-delegate',
  consult: 'is-consult',
  notify: 'is-notify',
  broadcast: 'is-broadcast',
};

const renderMessageContent = (content: unknown) => {
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content);
  } catch {
    return 'Structured agent payload';
  }
};

export function AgentLaboratory({
  topics,
  selectedTopics,
  count,
  difficulty,
  mode,
  questionType,
  running,
  messages,
  result,
  error,
  onToggleTopic,
  onCountChange,
  onDifficultyChange,
  onModeChange,
  onQuestionTypeChange,
  onStart,
  onStop,
  onOpenStudio,
}: AgentLaboratoryProps) {
  return (
    <section className="agent-laboratory" aria-labelledby="agent-lab-title">
      <header className="agent-lab-header">
        <div>
          <p className="academic-kicker">COLLABORATIVE INTELLIGENCE · CONTROLLED EXPERIMENT</p>
          <h1 id="agent-lab-title">Agent Laboratory</h1>
          <span>Configure, observe, and evaluate multi-agent calculus dataset synthesis.</span>
        </div>
        <div className={`laboratory-state ${running ? 'is-running' : ''}`}>
          <Activity size={16} /> {running ? 'Experiment active' : 'Laboratory ready'}
        </div>
      </header>

      <div className="agent-lab-grid">
        <aside className="laboratory-panel lab-configuration">
          <div className="laboratory-panel-heading">
            <span>01</span><div><small>Experiment protocol</small><h2>Synthesis controls</h2></div>
          </div>

          <div className="lab-field">
            <label>Curriculum domains <span>{selectedTopics.length} selected</span></label>
            <div className="lab-topic-list">
              {topics.map((topic) => (
                <button
                  type="button"
                  key={topic}
                  onClick={() => onToggleTopic(topic)}
                  className={selectedTopics.includes(topic) ? 'is-selected' : ''}
                  aria-pressed={selectedTopics.includes(topic)}
                >
                  <span className="topic-check">{selectedTopics.includes(topic) ? '✓' : '+'}</span>
                  {topic}
                </button>
              ))}
            </div>
          </div>

          <div className="lab-range-grid">
            <label>
              <span>Target count <strong>{count}</strong></span>
              <input type="range" min="1" max="20" value={count} onChange={(event) => onCountChange(Number(event.target.value))} />
            </label>
            <label>
              <span>Difficulty <strong>{difficulty}</strong></span>
              <input type="range" min="1" max="5" value={difficulty} onChange={(event) => onDifficultyChange(Number(event.target.value))} />
            </label>
          </div>

          <div className="lab-field">
            <label>Study mode</label>
            <div className="academic-segmented">
              {['drill', 'exam'].map((value) => (
                <button type="button" key={value} onClick={() => onModeChange(value)} className={mode === value ? 'is-selected' : ''}>{value}</button>
              ))}
            </div>
          </div>

          <div className="lab-field">
            <label>Response format</label>
            <div className="question-type-grid">
              {[['calculation', 'Calc'], ['mcq', 'MCQ'], ['fill_in', 'Fill']].map(([value, label]) => (
                <button type="button" key={value} onClick={() => onQuestionTypeChange(value)} className={questionType === value ? 'is-selected' : ''}>{label}</button>
              ))}
            </div>
          </div>

          <div className="lab-run-actions">
            <button type="button" className="academic-primary" onClick={onStart} disabled={running || selectedTopics.length === 0}>
              {running ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
              {running ? 'Agents collaborating…' : 'Start synthesis'}
            </button>
            {running && <button type="button" className="lab-stop" onClick={onStop} aria-label="Stop synthesis"><Square size={15} /></button>}
          </div>
          {error && <p className="lab-error" role="alert">{error}</p>}
        </aside>

        <div className="laboratory-panel lab-observation">
          <div className="laboratory-panel-heading">
            <span>02</span><div><small>Live observation</small><h2>Agent activity timeline</h2></div>
          </div>

          {messages.length > 0 ? (
            <div className="agent-timeline" aria-live="polite">
              {messages.map((message, index) => (
                <article key={`${message.sender}-${index}`} className={`agent-event ${MESSAGE_COLORS[message.type || 'notify'] || 'is-notify'}`}>
                  <div className="agent-event-marker"><MessageSquareText size={13} /></div>
                  <div className="agent-event-content">
                    <div>
                      <strong>{message.sender || 'system'}</strong>
                      <ArrowRight size={12} />
                      <strong>{message.recipient || 'all agents'}</strong>
                      <span>{message.type || 'notify'}</span>
                    </div>
                    <p>{renderMessageContent(message.content).slice(0, 260)}</p>
                  </div>
                </article>
              ))}
              {running && <div className="agent-thinking"><Loader2 className="animate-spin" size={14} /> Awaiting the next agent action…</div>}
            </div>
          ) : (
            <div className="lab-empty-state">
              <div><BrainCircuit size={30} /></div>
              <h3>The observation chamber is ready</h3>
              <p>Select one or more topics and start an experiment to inspect collaboration between synthesizer, reviewer, scaffolder, and curator agents.</p>
            </div>
          )}
        </div>

        <aside className="laboratory-panel lab-results">
          <div className="laboratory-panel-heading">
            <span>03</span><div><small>Evaluation record</small><h2>Experiment metrics</h2></div>
          </div>

          <div className="agent-role-map">
            {[
              ['S', 'Synthesizer', 'Constructs problems'],
              ['R', 'Reviewer', 'Validates quality'],
              ['C', 'Curator', 'Checks coverage'],
            ].map(([initial, name, description]) => (
              <div key={name}><span>{initial}</span><div><strong>{name}</strong><small>{description}</small></div></div>
            ))}
          </div>

          {result ? (
            <div className="lab-result-card">
              <div className="lab-result-success"><CheckCircle2 size={17} /> Synthesis complete</div>
              <div className="lab-metric-grid">
                <div><small>Problems</small><strong>{result.total_problems ?? 0}</strong></div>
                <div><small>LLM calls</small><strong>{result.total_llm_calls ?? 0}</strong></div>
                <div><small>Messages</small><strong>{result.total_agent_messages ?? 0}</strong></div>
                <div><small>Duration</small><strong>{result.duration_seconds?.toFixed(1) ?? '0'}s</strong></div>
              </div>
              {result.statistics && (
                <dl className="lab-statistics">
                  <div><dt>Topics covered</dt><dd>{(result.statistics.topics_covered || []).join(', ') || '—'}</dd></div>
                  <div><dt>Average difficulty</dt><dd>{result.statistics.avg_difficulty?.toFixed(1) || '—'}</dd></div>
                  <div><dt>Average quality</dt><dd>{result.statistics.avg_quality_score?.toFixed(1) || '—'}</dd></div>
                  <div><dt>Termination</dt><dd>{result.terminated_by || '—'}</dd></div>
                </dl>
              )}
              <button type="button" onClick={onOpenStudio}>Open synthesized folio <ArrowRight size={14} /></button>
            </div>
          ) : (
            <div className="lab-awaiting-result">
              <Database size={22} />
              <p>Validated experiment statistics will appear here when synthesis is complete.</p>
            </div>
          )}

          <div className="lab-runtime-note">
            <FlaskConical size={14} />
            <span><small>Method</small><strong>Autonomous P-T-A loops</strong></span>
          </div>
          <div className="lab-runtime-note">
            <Sparkles size={14} />
            <span><small>Quality gate</small><strong>Deterministic + LLM review</strong></span>
          </div>
        </aside>
      </div>
    </section>
  );
}
