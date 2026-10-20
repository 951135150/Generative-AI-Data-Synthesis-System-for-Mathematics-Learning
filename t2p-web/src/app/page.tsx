'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import SignatureCanvas from 'react-signature-canvas';
import { BrainCircuit, Database, ShieldCheck, Sparkles } from 'lucide-react';

import { useUser } from '@/context/UserContext';
import { AcademicTopbar } from '@/features/workspace/AcademicTopbar';
import { AgentLaboratory } from '@/features/workspace/AgentLaboratory';
import { GenerationRail } from '@/features/workspace/GenerationRail';
import { ProblemWorkspace } from '@/features/workspace/ProblemWorkspace';
import { SessionRail } from '@/features/workspace/SessionRail';
import type {
  AgentMessage,
  AuditResult,
  GeneratePayload,
  Problem,
  SynthesisResult,
  WorkspaceView,
} from '@/features/workspace/types';
import {
  api,
  API_BASE,
  AUDIT_TIMEOUT_MS,
  GENERATION_TIMEOUT_MS,
  getApiErrorMessage,
} from '@/lib/api';

const STORAGE_PROBLEMS = 't2p_problems';
const STORAGE_AUDITS = 't2p_audits';

const isSerializable = (value: unknown) => {
  try {
    JSON.stringify(value);
    return true;
  } catch {
    return false;
  }
};

const isProblem = (value: unknown): value is Problem => {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<Problem>;
  return typeof candidate.id === 'string'
    && typeof candidate.topic === 'string'
    && typeof candidate.problem_statement === 'string'
    && typeof candidate.difficulty === 'number';
};

const AUDIT_TIMEOUT_MESSAGE = 'AI review timed out after 3 minutes. The backend may still be processing; please wait before submitting again.';

export default function CalculusAtelierHome() {
  const {
    userId,
    setUserId,
    password,
    setPassword,
    authenticated,
    authReady,
    login,
    register,
    logout,
  } = useUser();

  const [mounted, setMounted] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [activeView, setActiveView] = useState<WorkspaceView>('studio');
  const [activeProblemIndex, setActiveProblemIndex] = useState(0);
  const previousProblemCountRef = useRef(0);

  const [loading, setLoading] = useState(false);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submittingProblems, setSubmittingProblems] = useState<Record<string, boolean>>({});
  const [auditResult, setAuditResult] = useState<Record<string, AuditResult>>({});
  const [selectedMCQChoices, setSelectedMCQChoices] = useState<Record<string, string>>({});
  const [selectedImages, setSelectedImages] = useState<Record<string, string>>({});
  const [scaffoldingVisible, setScaffoldingVisible] = useState<Record<string, boolean>>({});

  const signatureRefs = useRef<Record<string, SignatureCanvas | null>>({});
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const cameraInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const [selectedTopic, setSelectedTopic] = useState('');
  const [selectedMode, setSelectedMode] = useState('drill');
  const [difficulty, setDifficulty] = useState(3);
  const [topicOptions, setTopicOptions] = useState<string[]>([]);
  const [questionType, setQuestionType] = useState('calculation');
  const [visionOCRAvailable, setVisionOCRAvailable] = useState<boolean | null>(null);
  const [aiMode, setAiMode] = useState('');
  const [runtimeDevice, setRuntimeDevice] = useState('');
  const [simulationTopics, setSimulationTopics] = useState<string[]>([]);
  const [textAnswers, setTextAnswers] = useState<Record<string, string>>({});
  const attemptKeys = useRef<Record<string, { fingerprint: string; key: string }>>({});

  const attemptId = (problemId: string, fingerprint: string) => {
    const previous = attemptKeys.current[problemId];
    if (previous?.fingerprint === fingerprint) return previous.key;
    const key = crypto.randomUUID();
    attemptKeys.current[problemId] = { fingerprint, key };
    return key;
  };

  const [synthesisTopics, setSynthesisTopics] = useState<string[]>([]);
  const [synthesisCount, setSynthesisCount] = useState(5);
  const [synthesisDifficulty, setSynthesisDifficulty] = useState(3);
  const [synthesisMode, setSynthesisMode] = useState('drill');
  const [synthesisType, setSynthesisType] = useState('calculation');
  const [synthesisRunning, setSynthesisRunning] = useState(false);
  const [synthesisLog, setSynthesisLog] = useState<AgentMessage[]>([]);
  const [synthesisResult, setSynthesisResult] = useState<SynthesisResult | null>(null);
  const [synthesisError, setSynthesisError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const fetchTopics = useCallback(async () => {
    try {
      const response = await api.get('/topics');
      if (response.data.success) {
        const topics: string[] = response.data.topics;
        setTopicOptions(topics);
        setSelectedTopic((current) => current || topics[0] || '');
      }
    } catch {
      setError(`Unable to connect to the backend at ${API_BASE}. Confirm that api_server.py is running.`);
    }
  }, []);

  const fetchCapabilities = useCallback(async () => {
    try {
      const response = await api.get('/capabilities');
      setVisionOCRAvailable(Boolean(response.data?.vision_ocr?.configured));
      setAiMode(String(response.data?.ai_mode || ''));
      setRuntimeDevice(String(response.data?.rag?.device || 'not_loaded'));
      setSimulationTopics(response.data?.simulation_topics || []);
    } catch {
      setVisionOCRAvailable(false);
    }
  }, []);

  useEffect(() => {
    try {
      const savedProblems = localStorage.getItem(STORAGE_PROBLEMS);
      if (savedProblems) {
        const parsed: unknown = JSON.parse(savedProblems);
        if (Array.isArray(parsed)) {
          setProblems(parsed.filter((item): item is Problem => isSerializable(item) && isProblem(item)));
        }
      }

      const savedAudits = localStorage.getItem(STORAGE_AUDITS);
      if (savedAudits) {
        const parsed: unknown = JSON.parse(savedAudits);
        if (parsed && typeof parsed === 'object') {
          const safeAudits: Record<string, AuditResult> = {};
          Object.entries(parsed).forEach(([id, value]) => {
            if (isSerializable(value)) safeAudits[id] = value as AuditResult;
          });
          setAuditResult(safeAudits);
        }
      }
    } catch (restoreError) {
      console.warn('Failed to restore the local exercise folio.', restoreError);
    }

    setInitialized(true);
    setMounted(true);
    void fetchTopics();
    void fetchCapabilities();
  }, [fetchCapabilities, fetchTopics]);

  useEffect(() => {
    if (!initialized) return;
    try {
      localStorage.setItem(STORAGE_PROBLEMS, JSON.stringify(problems));
    } catch (storageError) {
      console.error('Failed to persist the exercise folio.', storageError);
    }
  }, [initialized, problems]);

  useEffect(() => {
    if (!initialized) return;
    try {
      localStorage.setItem(STORAGE_AUDITS, JSON.stringify(auditResult));
    } catch (storageError) {
      console.error('Failed to persist mentor reviews.', storageError);
    }
  }, [auditResult, initialized]);

  useEffect(() => {
    if (problems.length > previousProblemCountRef.current) {
      setActiveProblemIndex(Math.max(0, problems.length - 1));
    } else if (activeProblemIndex >= problems.length) {
      setActiveProblemIndex(Math.max(0, problems.length - 1));
    }
    previousProblemCountRef.current = problems.length;
  }, [activeProblemIndex, problems.length]);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  const handleLogin = async () => {
    const success = await login();
    window.alert(success ? `User ${userId} signed in securely.` : 'Login failed. Check the user ID and password.');
  };

  const handleRegister = async () => {
    const success = await register();
    window.alert(success ? `Account ${userId} created and signed in.` : 'Registration failed. Use a unique ID and a stronger password.');
  };

  const normalizeProblems = (value: unknown) => {
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is Problem => isSerializable(item) && isProblem(item));
  };

  const generateProblems = async () => {
    if (!selectedTopic) {
      setError('Select a curriculum topic before generating an exercise.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload: GeneratePayload = {
        topics: [selectedTopic],
        num: 1,
        mode: selectedMode,
        difficulty,
        question_type: questionType,
      };
      if (authenticated && userId) payload.user_id = userId;

      const response = await api.post('/generate', payload, { timeout: GENERATION_TIMEOUT_MS });
      const safeProblems = normalizeProblems(response.data.data);
      if (safeProblems.length > 0) {
        setProblems((current) => [...current, ...safeProblems]);
        void fetchCapabilities();
      } else {
        setError('Generation completed, but the returned problem did not match the expected schema.');
      }
    } catch (generationError) {
      setError(getApiErrorMessage(
        generationError,
        'Generation failed. Check the backend logs and try again.',
        'AI generation timed out after 3 minutes. The backend may still be processing; wait before trying again.',
      ));
    } finally {
      setLoading(false);
    }
  };

  const adaptiveGenerate = async () => {
    if (!authenticated || !userId) {
      window.alert('Please sign in before using adaptive learning.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await api.post(
        '/generate',
        { topics: [], num: 1, user_id: userId },
        { timeout: GENERATION_TIMEOUT_MS },
      );
      const safeProblems = normalizeProblems(response.data.data);
      if (safeProblems.length > 0) {
        setProblems((current) => [...current, ...safeProblems]);
        void fetchCapabilities();
      } else {
        setError('The adaptive recommendation returned an invalid problem. Please try again.');
      }
    } catch (generationError) {
      setError(getApiErrorMessage(
        generationError,
        'Adaptive generation failed. Check the backend logs and try again.',
        'AI generation timed out after 3 minutes. The backend may still be processing; wait before trying again.',
      ));
    } finally {
      setLoading(false);
    }
  };

  const startSynthesis = () => {
    if (synthesisTopics.length === 0) {
      setSynthesisError('Select at least one topic.');
      return;
    }

    eventSourceRef.current?.close();
    setSynthesisRunning(true);
    setSynthesisError(null);
    setSynthesisLog([]);
    setSynthesisResult(null);

    const params = new URLSearchParams({
      topics: synthesisTopics.join(','),
      count: String(synthesisCount),
      mode: synthesisMode,
      difficulty: String(synthesisDifficulty),
      question_type: synthesisType,
    });
    const eventSource = new EventSource(`${API_BASE}/synthesize/stream?${params}`);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as AgentMessage & SynthesisResult;
        if (data.event === 'complete') {
          setSynthesisResult(data);
          setSynthesisRunning(false);
          eventSource.close();
          const safeProblems = normalizeProblems(data.problems);
          if (safeProblems.length > 0) setProblems((current) => [...current, ...safeProblems]);
        } else {
          setSynthesisLog((current) => [...current, data]);
        }
      } catch {
        // Heartbeats and partial messages are intentionally ignored.
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      setSynthesisRunning(false);
      setSynthesisError('The synthesis stream was interrupted. Check the backend connection.');
    };
  };

  const stopSynthesis = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setSynthesisRunning(false);
  };

  const toggleSynthesisTopic = (topic: string) => {
    setSynthesisTopics((current) => current.includes(topic)
      ? current.filter((item) => item !== topic)
      : [...current, topic]);
  };

  const setProblemSubmitting = (problemId: string, value: boolean) => {
    setSubmittingProblems((current) => ({ ...current, [problemId]: value }));
  };

  const persistResult = (problem: Problem, data: Record<string, unknown>) => {
    const result: AuditResult = {
      is_correct: Boolean(data.is_correct),
      logic_alignment_score: Number(data.logic_alignment_score || 0),
      error_analysis: String(data.error_analysis || ''),
      tutor_feedback: String(data.tutor_feedback || ''),
      next_hint: String(data.next_hint || ''),
      ocr_text: String(data.ocr_text || ''),
      citations: Array.isArray(data.citations) ? data.citations : [],
      ai_mode: String(data.ai_mode || ''),
      grounding_status: String(data.grounding_status || ''),
      retrieval_method: String(data.retrieval_method || ''),
      progress_recorded: Boolean(data.progress_recorded),
    };
    setAuditResult((current) => ({ ...current, [problem.id]: result }));

    void fetchCapabilities();
  };

  const submitMCQ = async (problem: Problem, chosen: string) => {
    if (submittingProblems[problem.id]) return;
    setSelectedMCQChoices((current) => ({ ...current, [problem.id]: chosen }));
    setProblemSubmitting(problem.id, true);
    try {
      const response = await api.post('/audit', {
        problem_id: problem.id,
        selected_option: chosen,
        attempt_id: attemptId(problem.id, `mcq:${chosen}`),
        is_exam_mode: (problem.mode || selectedMode) === 'exam',
        user_id: authenticated && userId ? userId : undefined,
      }, { timeout: AUDIT_TIMEOUT_MS });
      if (response.data.success) persistResult(problem, response.data);
    } catch (auditError) {
      console.error('Submission failed', auditError);
      window.alert(getApiErrorMessage(auditError, 'Audit services are temporarily unavailable. Please try again.', AUDIT_TIMEOUT_MESSAGE));
    } finally {
      setProblemSubmitting(problem.id, false);
    }
  };

  const handleAISubmission = async (problem: Problem) => {
    if (submittingProblems[problem.id]) return;
    const selectedImage = selectedImages[problem.id];
    const typedAnswer = textAnswers[problem.id]?.trim();
    const canvas = signatureRefs.current[problem.id];
    const payload = selectedImage
      || (canvas && !canvas.isEmpty() ? canvas.getTrimmedCanvas().toDataURL('image/png') : '');

    if (!payload && !typedAnswer) {
      window.alert('Write your derivation or upload a photograph before requesting an AI review.');
      return;
    }

    setProblemSubmitting(problem.id, true);
    try {
      const response = await api.post('/audit', {
        problem_id: problem.id,
        student_work_image: payload || undefined,
        text_answer: typedAnswer || undefined,
        attempt_id: attemptId(problem.id, typedAnswer || payload),
        is_exam_mode: (problem.mode || selectedMode) === 'exam',
        user_id: authenticated && userId ? userId : undefined,
      }, { timeout: AUDIT_TIMEOUT_MS });
      if (response.data.success) persistResult(problem, response.data);
    } catch (auditError) {
      console.error('Submission failed', auditError);
      window.alert(getApiErrorMessage(auditError, 'Audit services are temporarily unavailable. Please try again.', AUDIT_TIMEOUT_MESSAGE));
    } finally {
      setProblemSubmitting(problem.id, false);
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>, problemId: string) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      setSelectedImages((current) => ({ ...current, [problemId]: String(reader.result || '') }));
      signatureRefs.current[problemId]?.clear();
    };
    reader.readAsDataURL(file);
  };

  const removeSelectedImage = (problemId: string) => {
    setSelectedImages((current) => {
      const next = { ...current };
      delete next[problemId];
      return next;
    });
  };

  const clearInput = (problemId: string) => {
    setTextAnswers(current => ({ ...current, [problemId]: '' }));
    signatureRefs.current[problemId]?.clear();
    removeSelectedImage(problemId);
    if (fileInputRefs.current[problemId]) fileInputRefs.current[problemId]!.value = '';
    if (cameraInputRefs.current[problemId]) cameraInputRefs.current[problemId]!.value = '';
  };

  const clearAll = () => {
    setProblems([]);
    setAuditResult({});
    setSelectedMCQChoices({});
    setSelectedImages({});
    setTextAnswers({});
    setSubmittingProblems({});
    setActiveProblemIndex(0);
    localStorage.removeItem(STORAGE_PROBLEMS);
    localStorage.removeItem(STORAGE_AUDITS);
  };

  const activeProblem = problems[activeProblemIndex];
  const activeReview = activeProblem ? auditResult[activeProblem.id] : undefined;
  const activeSubmitting = activeProblem ? Boolean(submittingProblems[activeProblem.id]) : false;

  if (!mounted) return null;

  return (
    <div className="workspace-app">
      <div className="academic-rule" />
      <AcademicTopbar
        activeView={activeView}
        onViewChange={setActiveView}
        userId={userId}
        password={password}
        authenticated={authenticated}
        authReady={authReady}
        onUserIdChange={setUserId}
        onPasswordChange={setPassword}
        onLogin={() => void handleLogin()}
        onRegister={() => void handleRegister()}
        onLogout={() => void logout()}
      />

      <main className="workspace-main">
        {aiMode && (
          <div className="runtime-notice" role="status">
            <strong>{aiMode === 'simulation' ? 'Offline AI simulation' : 'Live AI mode'}</strong>
            <span>{aiMode === 'simulation'
              ? 'No paid model calls. Questions and role replies use explicit fixtures; retrieval and learning records run locally.'
              : 'External model access is enabled.'}</span>
            <small>Embeddings: {runtimeDevice === 'not_loaded' ? 'loads on first use' : runtimeDevice}</small>
          </div>
        )}
        {activeView === 'studio' ? (
          <>
            <section className="workspace-intro">
              <div>
                <p className="academic-kicker">UNIVERSITAS · MATHEMATICA · MMXXVI</p>
                <h1>Deliberate practice for <em>mathematical reasoning.</em></h1>
                <span>Generate, solve, and review validated calculus problems in a focused academic workspace.</span>
              </div>
              <div className="workspace-intro-metadata">
                <span><Database size={14} /><small>Corpus</small><strong>Dataset v3.1</strong></span>
                <span><ShieldCheck size={14} /><small>Quality</small><strong>Deterministic gates</strong></span>
                <span><BrainCircuit size={14} /><small>Intelligence</small><strong>Agentic review</strong></span>
              </div>
            </section>

            <div className="workspace-grid">
              <GenerationRail
                topics={aiMode === 'simulation' ? topicOptions.filter(t => simulationTopics.includes(t)) : topicOptions}
                selectedTopic={selectedTopic}
                selectedMode={selectedMode}
                difficulty={difficulty}
                questionType={questionType}
                loading={loading}
                error={error}
                onTopicChange={setSelectedTopic}
                onModeChange={setSelectedMode}
                onDifficultyChange={setDifficulty}
                onQuestionTypeChange={setQuestionType}
                onRefreshTopics={() => void fetchTopics()}
                onGenerate={() => void generateProblems()}
                onAdaptiveGenerate={() => void adaptiveGenerate()}
              />

              <ProblemWorkspace
                problem={activeProblem}
                problemIndex={activeProblemIndex}
                totalProblems={problems.length}
                result={activeReview}
                selectedMCQChoice={activeProblem ? selectedMCQChoices[activeProblem.id] : undefined}
                selectedImage={activeProblem ? selectedImages[activeProblem.id] : undefined}
                visionOCRAvailable={visionOCRAvailable}
                textAnswer={activeProblem ? textAnswers[activeProblem.id] || '' : ''}
                onTextAnswerChange={(id, value) => setTextAnswers(current => ({ ...current, [id]: value }))}
                submitting={activeSubmitting}
                generating={loading}
                showScaffolding={activeProblem ? Boolean(scaffoldingVisible[activeProblem.id]) : false}
                onSignatureRef={(problemId, instance) => { signatureRefs.current[problemId] = instance; }}
                onFileInputRef={(problemId, element) => { fileInputRefs.current[problemId] = element; }}
                onCameraInputRef={(problemId, element) => { cameraInputRefs.current[problemId] = element; }}
                onOpenFilePicker={(problemId) => fileInputRefs.current[problemId]?.click()}
                onOpenCamera={(problemId) => cameraInputRefs.current[problemId]?.click()}
                onPrevious={() => setActiveProblemIndex((current) => Math.max(0, current - 1))}
                onNext={() => setActiveProblemIndex((current) => Math.min(problems.length - 1, current + 1))}
                onClearAll={clearAll}
                onGenerate={() => void generateProblems()}
                onToggleScaffolding={(problemId) => setScaffoldingVisible((current) => ({ ...current, [problemId]: !current[problemId] }))}
                onSubmitMCQ={(problem, choice) => void submitMCQ(problem, choice)}
                onSubmitWritten={(problem) => void handleAISubmission(problem)}
                onFileChange={handleFileChange}
                onClearInput={clearInput}
                onRemoveImage={removeSelectedImage}
              />

              <SessionRail
                problems={problems}
                activeIndex={activeProblemIndex}
                activeProblem={activeProblem}
                result={activeReview}
                generating={loading}
                auditing={activeSubmitting}
                onSelectProblem={setActiveProblemIndex}
                onOpenAgents={() => setActiveView('agents')}
              />
            </div>
          </>
        ) : (
          <AgentLaboratory
                topics={aiMode === 'simulation' ? topicOptions.filter(t => simulationTopics.includes(t)) : topicOptions}
            selectedTopics={synthesisTopics}
            count={synthesisCount}
            difficulty={synthesisDifficulty}
            mode={synthesisMode}
            questionType={synthesisType}
            running={synthesisRunning}
            messages={synthesisLog}
            result={synthesisResult}
            error={synthesisError}
            onToggleTopic={toggleSynthesisTopic}
            onCountChange={setSynthesisCount}
            onDifficultyChange={setSynthesisDifficulty}
            onModeChange={setSynthesisMode}
            onQuestionTypeChange={setSynthesisType}
            onStart={startSynthesis}
            onStop={stopSynthesis}
            onOpenStudio={() => setActiveView('studio')}
          />
        )}

        <footer className="workspace-footer">
          <span><Sparkles size={13} /> Calculus Atelier</span>
          <span>Adaptive learning · Validated generation · Agentic synthesis</span>
        </footer>
      </main>
    </div>
  );
}
