'use client';

import {
  BookOpen,
  ChevronRight,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';

interface GenerationRailProps {
  topics: string[];
  selectedTopic: string;
  selectedMode: string;
  difficulty: number;
  questionType: string;
  loading: boolean;
  error: string | null;
  onTopicChange: (value: string) => void;
  onModeChange: (value: string) => void;
  onDifficultyChange: (value: number) => void;
  onQuestionTypeChange: (value: string) => void;
  onRefreshTopics: () => void;
  onGenerate: () => void;
  onAdaptiveGenerate: () => void;
}

const QUESTION_TYPES = [
  { key: 'mcq', label: 'Multiple choice', shortLabel: 'MCQ' },
  { key: 'fill_in', label: 'Fill in', shortLabel: 'Fill' },
  { key: 'calculation', label: 'Calculation', shortLabel: 'Calc' },
];

export function GenerationRail({
  topics,
  selectedTopic,
  selectedMode,
  difficulty,
  questionType,
  loading,
  error,
  onTopicChange,
  onModeChange,
  onDifficultyChange,
  onQuestionTypeChange,
  onRefreshTopics,
  onGenerate,
  onAdaptiveGenerate,
}: GenerationRailProps) {
  return (
    <aside className="workspace-rail generation-rail" aria-label="Problem configuration">
      <div className="rail-heading">
        <span>01</span>
        <div>
          <p>Study protocol</p>
          <h2>Configure exercise</h2>
        </div>
      </div>

      <div className="configuration-summary">
        <BookOpen size={17} />
        <div>
          <small>Current inquiry</small>
          <strong>{selectedTopic || 'Loading curriculum…'}</strong>
        </div>
      </div>

      <div className="rail-field">
        <label htmlFor="workspace-topic">
          Knowledge dimension
          <button type="button" onClick={onRefreshTopics} aria-label="Refresh topics">
            <RefreshCw size={12} />
          </button>
        </label>
          <div className="academic-select-wrap">
            <select
              id="workspace-topic"
              value={selectedTopic}
              onChange={(event) => onTopicChange(event.target.value)}
              disabled={topics.length === 0}
              aria-describedby={topics.length === 0 ? 'workspace-topic-status' : undefined}
            >
              {topics.length === 0 ? (
                <option value="">Waiting for curriculum data…</option>
              ) : (
                topics.map((topic) => <option key={topic} value={topic}>{topic}</option>)
              )}
            </select>
          </div>
          {topics.length === 0 && (
            <p id="workspace-topic-status" className="rail-field-status" role="status">
              The knowledge catalogue is unavailable. Check the API connection and refresh.
            </p>
          )}
      </div>

      <fieldset className="rail-field">
        <legend>Practice mode</legend>
        <div className="academic-segmented">
          {['drill', 'exam'].map((mode) => (
            <button
              type="button"
              key={mode}
              onClick={() => onModeChange(mode)}
              className={selectedMode === mode ? 'is-selected' : ''}
              aria-pressed={selectedMode === mode}
            >
              {mode}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="rail-field difficulty-field">
        <label htmlFor="workspace-difficulty">
          Difficulty coefficient <strong>Level {difficulty}</strong>
        </label>
        <input
          id="workspace-difficulty"
          type="range"
          min="1"
          max="5"
          value={difficulty}
          onChange={(event) => onDifficultyChange(Number(event.target.value))}
        />
        <div className="difficulty-scale" aria-hidden="true">
          {['I', 'II', 'III', 'IV', 'V'].map((level, index) => (
            <span key={level} className={index < difficulty ? 'is-filled' : ''}>{level}</span>
          ))}
        </div>
      </div>

      <fieldset className="rail-field">
        <legend>Response format</legend>
        <div className="question-type-grid">
          {QUESTION_TYPES.map(({ key, label, shortLabel }) => (
            <button
              type="button"
              key={key}
              title={label}
              onClick={() => onQuestionTypeChange(key)}
              className={questionType === key ? 'is-selected' : ''}
              aria-pressed={questionType === key}
            >
              {shortLabel}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="rail-actions">
        <button
          type="button"
          onClick={onGenerate}
          disabled={loading || !selectedTopic}
          className="academic-primary"
        >
          {loading ? <Loader2 className="animate-spin" size={17} /> : <Sparkles size={17} />}
          {loading ? 'Generating and reviewing…' : 'Generate current configuration question'}
        </button>
        <button
          type="button"
          onClick={onAdaptiveGenerate}
          disabled={loading}
          className="academic-secondary"
        >
          AI recommendation <ChevronRight size={15} />
        </button>
      </div>

      {loading && (
        <div className="rail-notice is-progress" role="status" aria-live="polite">
          <Loader2 className="animate-spin" size={14} />
          <span>Generation and quality review usually take 1–2 minutes. Keep this page open.</span>
        </div>
      )}
      {error && <div className="rail-notice is-error" role="alert">{error}</div>}
    </aside>
  );
}
