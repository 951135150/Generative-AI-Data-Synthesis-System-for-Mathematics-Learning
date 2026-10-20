'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Bar,
  BarChart,
  CartesianGrid,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowLeft,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Lightbulb,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Target,
  Trophy,
} from 'lucide-react';

import { useUser } from '@/context/UserContext';
import { api, getApiErrorMessage } from '@/lib/api';
import {
  aggregateMasteryDomains,
  formatStudyTime,
  getAcademicStanding,
  getCourseGrade,
  getLearningBrief,
  getTopicChartLabel,
} from '@/lib/progress';

interface TopicProgress {
  mastery_score: number;
  current_level: number;
  completed_count: number;
}

type ProgressMap = Record<string, TopicProgress>;

export default function Dashboard() {
  const { userId, authenticated, authReady } = useUser();
  const [data, setData] = useState<ProgressMap | null>(null);
  const [totalMinutes, setTotalMinutes] = useState(0);
  const [recommendation, setRecommendation] = useState<{ topic: string; reason: string; difficulty: number } | null>(null);
  const [conceptEvidence, setConceptEvidence] = useState<Array<{ concept_id: string; attempts: number; correct: number; evidence_status: string }>>([]);
  const [reviewQueue, setReviewQueue] = useState<Array<{ topic: string; overdue_days: number; interval_days: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchProgress = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(`/user/progress/${userId}`);
      if (response.data.success) {
        setData(response.data.topics_status);
        setTotalMinutes(Number(response.data.total_minutes) || 0);
        setRecommendation(response.data.recommendation || null);
        setConceptEvidence(response.data.concept_evidence || []);
        setReviewQueue(response.data.review_queue || []);
      }
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, 'Unable to retrieve the academic record. Confirm that the backend is running.'));
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (authenticated && userId) void fetchProgress();
  }, [authenticated, fetchProgress, userId]);

  const entries = useMemo(() => Object.entries(data || {}), [data]);
  const summary = useMemo(() => {
    if (entries.length === 0) {
      return {
        averageMastery: 0,
        completed: 0,
        strongestTopic: 'Awaiting evidence',
        strongestScore: 0,
        weakestTopic: 'Awaiting evidence',
        weakestScore: 0,
        courseGrade: 'F',
        standing: 'Foundation',
      };
    }
    const completed = entries.reduce((sum, [, value]) => sum + value.completed_count, 0);
    const averageMastery = Math.round(
      entries.reduce((sum, [, value]) => sum + value.mastery_score, 0) / entries.length * 100,
    );
    const strongest = entries.reduce((best, current) => (
      current[1].mastery_score > best[1].mastery_score ? current : best
    ));
    const weakest = entries.reduce((lowest, current) => (
      current[1].mastery_score < lowest[1].mastery_score ? current : lowest
    ));
    return {
      averageMastery,
      completed,
      strongestTopic: strongest[0],
      strongestScore: Math.round(strongest[1].mastery_score * 100),
      weakestTopic: weakest[0],
      weakestScore: Math.round(weakest[1].mastery_score * 100),
      courseGrade: getCourseGrade(averageMastery),
      standing: getAcademicStanding(averageMastery),
    };
  }, [entries]);
  const learningBrief = getLearningBrief(
    summary.averageMastery,
    summary.strongestTopic,
    summary.weakestTopic,
  );

  const radarData = useMemo(() => aggregateMasteryDomains(
    Object.fromEntries(entries.map(([topic, info]) => [topic, info.mastery_score])),
  ), [entries]);

  const barData = entries.map(([topic, info]) => ({
    topic: getTopicChartLabel(topic),
    level: info.current_level,
    completed: info.completed_count,
  }));

  if (!authReady) {
    return (
      <div className="progress-gate">
        <Loader2 className="animate-spin" size={30} />
        <p>Restoring the academic record…</p>
      </div>
    );
  }

  if (!authenticated || !userId) {
    return (
      <div className="progress-gate">
        <div className="progress-gate-card">
          <BrainCircuit size={32} />
          <p className="academic-kicker">PROTECTED ACADEMIC RECORD</p>
          <h1>Sign in to review your progress.</h1>
          <span>Learning evidence is linked to an authenticated student account.</span>
          <Link href="/"><ArrowLeft size={15} /> Return to Problem Studio</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-app progress-workspace">
      <div className="academic-rule" />
      <header className="progress-topbar">
        <Link href="/" className="workspace-brand">
          <span className="workspace-brand-seal"><BrainCircuit size={19} /></span>
          <span><strong>Calculus Atelier</strong><small>Reasoning Studio</small></span>
        </Link>
        <div className="progress-account"><ShieldCheck size={15} /> {userId}</div>
        <Link href="/" className="progress-return"><ArrowLeft size={15} /> Problem Studio</Link>
      </header>

      <main className="progress-main">
        <section className="progress-hero">
          <div>
            <p className="academic-kicker">STUDENT RECORD · EVIDENCE-BASED LEARNING</p>
            <h1>Academic Progress Report</h1>
            <span>A structured record of calculus mastery, practice frequency, and the next learning priority.</span>
          </div>
          <button type="button" onClick={() => void fetchProgress()} disabled={loading}>
            <RefreshCw className={loading ? 'animate-spin' : ''} size={15} /> Refresh record
          </button>
        </section>

        {error && <div className="progress-error" role="alert">{error}</div>}

        <section className="progress-kpi-grid" aria-label="Progress summary">
          <article>
            <span><Target size={17} /></span>
            <div><small>Average mastery</small><strong>{summary.averageMastery}%</strong><p>Across {entries.length} recorded domains</p></div>
          </article>
          <article>
            <span><BookOpenCheck size={17} /></span>
            <div><small>Completed exercises</small><strong>{summary.completed}</strong><p>Validated attempts in the record</p></div>
          </article>
          <article>
            <span><Trophy size={17} /></span>
            <div><small>Strongest domain</small><strong className="is-topic">{summary.strongestTopic}</strong><p>{summary.strongestScore}% demonstrated mastery</p></div>
          </article>
          <article>
            <span><Clock3 size={17} /></span>
            <div><small>Course standing</small><strong>{summary.courseGrade}</strong><p>{summary.standing} · {formatStudyTime(totalMinutes)} documented study</p></div>
          </article>
        </section>

        {loading ? (
          <div className="progress-loading"><Loader2 className="animate-spin" size={26} /> Updating academic evidence…</div>
        ) : data && entries.length > 0 ? (
          <>
            <div className="progress-chart-grid">
              <section className="progress-panel mastery-domain-panel">
                <div className="progress-panel-heading">
                  <span>01</span>
                  <div><p>Competency profile</p><h2>Domain mastery</h2></div>
                  <small className="progress-panel-context">6-domain view · {entries.length} topics</small>
                </div>
                <div
                  className="mastery-radar"
                  role="img"
                  aria-label={`Aggregated calculus domain mastery: ${radarData.map((item) => `${item.domain} ${item.mastery}%`).join(', ')}`}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} outerRadius="67%">
                      <PolarGrid stroke="#d8d3c7" />
                      <PolarAngleAxis dataKey="domain" tick={{ fontSize: 10, fill: '#59605d' }} />
                      <PolarRadiusAxis domain={[0, 100]} axisLine={false} tick={false} />
                      <Radar
                        name="Average mastery (%)"
                        dataKey="mastery"
                        stroke="#183153"
                        strokeWidth={2}
                        fill="#183153"
                        fillOpacity={0.2}
                        dot={{ r: 3, fill: '#183153', strokeWidth: 0 }}
                        isAnimationActive={false}
                      />
                      <Tooltip formatter={(value) => [`${Number(value)}%`, 'Average mastery']} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mastery-domain-key" aria-label="Aggregated domain mastery values">
                  {radarData.map((item) => (
                    <div key={item.domain}>
                      <span>{item.domain}</span>
                      <strong>{item.mastery}%</strong>
                      <small>{item.topicCount} {item.topicCount === 1 ? 'topic' : 'topics'}</small>
                    </div>
                  ))}
                </div>
                <p className="mastery-method-note">Each domain is the unweighted mean of its recorded curriculum topics.</p>
              </section>

              <section className="progress-panel">
                <div className="progress-panel-heading"><span>02</span><div><p>Coursework record</p><h2>Level and frequency</h2></div></div>
                <div className="progress-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={barData} margin={{ top: 10, right: 10, left: -12, bottom: 35 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#ded9cc" />
                      <XAxis dataKey="topic" tick={{ fontSize: 9, fill: '#666d69' }} angle={-25} textAnchor="end" interval={0} />
                      <YAxis tick={{ fontSize: 9, fill: '#8a8d85' }} />
                      <Tooltip />
                      <Bar dataKey="level" fill="#477466" name="Current level" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="completed" fill="#a47c3c" name="Completed" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </div>

            <div className="progress-detail-grid">
              <section className="progress-panel topic-record-panel">
                <div className="progress-panel-heading"><span>03</span><div><p>Curriculum evidence</p><h2>Domain record</h2></div></div>
                <div className="topic-record-table">
                  <div className="topic-record-row is-heading"><span>Curriculum domain</span><span>Mastery</span><span>Level</span><span>Exercises</span></div>
                  {entries.map(([topic, info]) => (
                    <div className="topic-record-row" key={topic}>
                      <span>{topic}</span>
                      <span><i><b style={{ width: `${Math.round(info.mastery_score * 100)}%` }} /></i>{Math.round(info.mastery_score * 100)}%</span>
                      <span>Level {info.current_level}</span>
                      <span>{info.completed_count}</span>
                    </div>
                  ))}
                </div>
              </section>

              <aside className="progress-panel learning-brief">
                <div className="progress-panel-heading"><span>04</span><div><p>Mentor memorandum</p><h2>Learning brief</h2></div></div>
                <div className="learning-brief-seal"><Lightbulb size={22} /></div>
                <h3>{learningBrief.title}</h3>
                <p>{learningBrief.description}</p>
                {recommendation && <div className="recommended-task">
                  <small>Recommended next exercise · Level {recommendation.difficulty}</small>
                  <strong>{recommendation.topic}</strong>
                  <p>{recommendation.reason}</p>
                </div>}
                {conceptEvidence.length > 0 && <div className="recommended-task">
                  <small>Observed concept attempts · not a mastery estimate</small>
                  {conceptEvidence.slice(0, 4).map(item => <p key={item.concept_id}>
                    <strong>{item.concept_id.replaceAll('_', ' ')}</strong>: {item.correct}/{item.attempts} first attempts correct
                    {item.evidence_status === 'limited' ? ' · limited evidence' : ''}
                  </p>)}
                </div>}
                {reviewQueue.length > 0 && <div className="recommended-task">
                  <small>Scheduled review · based on recorded practice dates</small>
                  {reviewQueue.slice(0, 3).map(item => <p key={item.topic}>
                    <strong>{item.topic}</strong>: {item.overdue_days === 0 ? 'due today' : `${item.overdue_days} days overdue`}
                    {' '}· {item.interval_days}-day practice interval
                  </p>)}
                </div>}
                <ul>
                  <li><CheckCircle2 size={13} /> Generate one focused problem at a time.</li>
                  <li><CheckCircle2 size={13} /> Submit full reasoning for AI review.</li>
                  <li><CheckCircle2 size={13} /> Revisit the weakest recorded domain.</li>
                </ul>
                <Link href="/">Continue deliberate practice <ArrowLeft size={14} /></Link>
              </aside>
            </div>
          </>
        ) : (
          <div className="progress-empty">
            <BookOpenCheck size={30} />
            <h2>No learning evidence has been recorded yet.</h2>
            <p>Generate a problem, submit an answer, and request an AI mentor review to create your first progress entry.</p>
            <Link href="/">Begin in Problem Studio</Link>
          </div>
        )}
      </main>
    </div>
  );
}
