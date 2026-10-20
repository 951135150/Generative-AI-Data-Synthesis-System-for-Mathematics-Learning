'use client';

import type { ChangeEvent } from 'react';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import SignatureCanvas from 'react-signature-canvas';
import { BlockMath, InlineMath } from 'react-katex';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Camera,
  CheckCircle2,
  ChevronRight,
  FolderOpen,
  Lightbulb,
  Loader2,
  RotateCcw,
  Send,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';

import type { AuditResult, Problem } from './types';
import type { CourseCitation } from './types';
import { api } from '@/lib/api';

interface ProblemWorkspaceProps {
  problem?: Problem;
  problemIndex: number;
  totalProblems: number;
  result?: AuditResult;
  selectedMCQChoice?: string;
  selectedImage?: string;
  visionOCRAvailable: boolean | null;
  textAnswer?: string;
  onTextAnswerChange?: (id: string, value: string) => void;
  submitting: boolean;
  generating: boolean;
  showScaffolding: boolean;
  onSignatureRef: (problemId: string, instance: SignatureCanvas | null) => void;
  onFileInputRef: (problemId: string, element: HTMLInputElement | null) => void;
  onCameraInputRef: (problemId: string, element: HTMLInputElement | null) => void;
  onOpenFilePicker: (problemId: string) => void;
  onOpenCamera: (problemId: string) => void;
  onPrevious: () => void;
  onNext: () => void;
  onClearAll: () => void;
  onGenerate: () => void;
  onToggleScaffolding: (problemId: string) => void;
  onSubmitMCQ: (problem: Problem, choice: string) => void;
  onSubmitWritten: (problem: Problem) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>, problemId: string) => void;
  onClearInput: (problemId: string) => void;
  onRemoveImage: (problemId: string) => void;
}

const refineStatement = (text: string) => {
  if (!text || typeof text !== 'string') return '';
  let result = text;
  result = result.replace(/\\\\+/g, '\\');
  result = result.replace(/\\\(/g, '$').replace(/\\\)/g, '$');
  result = result.replace(/\\\[/g, '\n$$\n').replace(/\\\]/g, '\n$$\n');
  result = result.replace(/\\\$/g, '$');
  result = result.replace(/\\\s+begin\{/g, '\\begin{');
  result = result.replace(/\\\s+end\{/g, '\\end{');
  result = result.replace(/\\?(quad|qquad|enspace|thickspace|vspace\{.*?\}|hspace\{.*?\})/g, ' ');
  result = result.replace(/([a-zA-Z0-9\u4e00-\u9fa5])\$/g, '$1 $');
  result = result.replace(/\$([a-zA-Z0-9\u4e00-\u9fa5])/g, '$ $1');
  return result.replace(/\s+/g, ' ').trim();
};

const prepareOptionText = (text: string) => {
  if (!text) return text;
  if (/\$/.test(text)) return refineStatement(text);
  if (/\\[a-zA-Z]+/.test(text)) return `$${refineStatement(text)}$`;
  return refineStatement(text);
};

const renderMathContent = (text: string) => {
  if (!text) return null;
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$]+\$|\\\[[\s\S]*?\\\]|\\\(.*?\\\))/g);

  return parts.map((part, index) => {
    if ((part.startsWith('$$') && part.endsWith('$$')) || (part.startsWith('\\[') && part.endsWith('\\]'))) {
      return <BlockMath key={index} math={part.slice(2, -2)} />;
    }
    if ((part.startsWith('$') && part.endsWith('$')) || (part.startsWith('\\(') && part.endsWith('\\)'))) {
      const math = part.startsWith('$') ? part.slice(1, -1) : part.slice(2, -2);
      return <InlineMath key={index} math={math} />;
    }
    return <span key={index}>{part}</span>;
  });
};

export function ProblemWorkspace({
  problem,
  problemIndex,
  totalProblems,
  result,
  selectedMCQChoice,
  selectedImage,
  visionOCRAvailable,
  textAnswer = '',
  onTextAnswerChange,
  submitting,
  generating,
  showScaffolding,
  onSignatureRef,
  onFileInputRef,
  onCameraInputRef,
  onOpenFilePicker,
  onOpenCamera,
  onPrevious,
  onNext,
  onClearAll,
  onGenerate,
  onToggleScaffolding,
  onSubmitMCQ,
  onSubmitWritten,
  onFileChange,
  onClearInput,
  onRemoveImage,
}: ProblemWorkspaceProps) {
  const [source, setSource] = useState<CourseCitation | null>(null);
  const [sourceError, setSourceError] = useState('');
  const sourceDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (source && sourceDialog.current && !sourceDialog.current.open) sourceDialog.current.showModal();
  }, [source]);
  const openSource = async (citation: CourseCitation) => {
    setSource(null);
    setSourceError('');
    try {
      const response = await api.get(`/knowledge/chunks/${encodeURIComponent(citation.id)}`, {
        params: { content_hash: citation.content_hash, source_version: citation.source_version },
      });
      setSource({ ...response.data.data, citation_id: citation.citation_id });
    } catch {
      setSourceError('This source version has changed or is no longer available. Request a new review.');
    }
  };
  return (
    <section className="problem-workspace" aria-labelledby="problem-workspace-title">
      <header className="problem-workspace-header">
        <div>
          <p>02 · PRIMARY CANVAS</p>
          <h2 id="problem-workspace-title">Problem Workspace</h2>
        </div>
        <div className="workspace-pagination" aria-label="Problem navigation">
          <button type="button" onClick={onPrevious} disabled={problemIndex <= 0 || totalProblems === 0} aria-label="Previous problem">
            <ArrowLeft size={15} />
          </button>
          <span>{totalProblems > 0 ? `${String(problemIndex + 1).padStart(2, '0')} / ${String(totalProblems).padStart(2, '0')}` : '00 / 00'}</span>
          <button type="button" onClick={onNext} disabled={problemIndex >= totalProblems - 1 || totalProblems === 0} aria-label="Next problem">
            <ArrowRight size={15} />
          </button>
          {totalProblems > 0 && (
            <button type="button" onClick={onClearAll} className="clear-folio" aria-label="Clear all questions">
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </header>

      {problem ? (
        <article className="problem-paper workspace-paper">
          <div className="problem-folio">
            <span>EXERCISE {String(problemIndex + 1).padStart(2, '0')}</span>
            <span>LEVEL {['I', 'II', 'III', 'IV', 'V'][Number(problem.difficulty) - 1] || 'III'}</span>
          </div>

          <div className="problem-taxonomy">
            <span>{problem.topic}</span>
            <ChevronRight size={12} />
            <span>{problem.sub_topic || 'Core concept'}</span>
            <i />
            <small>{problem.question_type?.replace('_', ' ') || 'calculation'}</small>
          </div>

          <div className="math-renderer problem-statement">
            <ReactMarkdown
              remarkPlugins={[remarkMath]}
              rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
            >
              {refineStatement(problem.problem_statement)}
            </ReactMarkdown>
          </div>

          {problem.scaffolding && problem.scaffolding.length > 0 && (
            <section className="scaffolding-section">
              <button type="button" onClick={() => onToggleScaffolding(problem.id)} aria-expanded={showScaffolding}>
                <Lightbulb size={14} /> {showScaffolding ? 'Close research prompts' : 'Open research prompts'}
              </button>
              {showScaffolding && (
                <ol>
                  {problem.scaffolding.map((item) => (
                    <li key={item.step}>
                      <span>{String(item.step).padStart(2, '0')}</span>
                      <ReactMarkdown
                        remarkPlugins={[remarkMath]}
                        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                        components={{ p: ({ children }) => <p>{children}</p> }}
                      >
                        {refineStatement(item.hint)}
                      </ReactMarkdown>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          {problem.question_type === 'mcq' && problem.options ? (
            <section className="answer-section mcq-section" aria-labelledby={`answer-${problem.id}`}>
              <div className="answer-section-heading">
                <div><small>Response workspace</small><h3 id={`answer-${problem.id}`}>Select the strongest conclusion</h3></div>
                {submitting ? (
                  <span><Loader2 className="animate-spin" size={13} /> AI mentor reviewing…</span>
                ) : selectedMCQChoice ? (
                  <span className="mcq-selection-status"><CheckCircle2 size={13} /> Option {selectedMCQChoice} selected</span>
                ) : null}
              </div>
              <div className="mcq-grid">
                {Object.entries(problem.options).map(([key, value]) => {
                  const isSelected = selectedMCQChoice === key;
                  return (
                    <button
                      type="button"
                      key={key}
                      className={isSelected ? 'is-selected' : undefined}
                      aria-label={`Option ${key}: ${value}`}
                      aria-pressed={isSelected}
                      onClick={() => onSubmitMCQ(problem, key)}
                      disabled={submitting}
                    >
                      <span>{key}</span>
                      <ReactMarkdown
                        remarkPlugins={[remarkMath]}
                        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                        components={{ p: ({ children }) => <span>{children}</span> }}
                      >
                        {prepareOptionText(value)}
                      </ReactMarkdown>
                      {isSelected && (
                        <span className="mcq-selected-indicator" aria-hidden="true">
                          <CheckCircle2 size={14} /> Selected
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          ) : (
            <section className="answer-section written-section" aria-labelledby={`draft-${problem.id}`}>
              <div className="answer-section-heading">
                <div><small>Response workspace</small><h3 id={`draft-${problem.id}`}>{problem.ai_mode === 'simulation' ? 'Mathematical answer' : 'Handwritten mathematical draft'}</h3></div>
                <button type="button" onClick={() => onClearInput(problem.id)} aria-label="Clear handwritten input">
                  <RotateCcw size={15} /> Clear
                </button>
              </div>
              <label className="typed-answer">
                <span>{problem.ai_mode === 'simulation' ? 'Final expression · offline checking' : 'Typed mathematical answer'}</span>
                <textarea value={textAnswer} onChange={event => onTextAnswerChange?.(problem.id, event.target.value)}
                  placeholder="Use SymPy notation, for example 6*x+2 or (3*x+1)**2" rows={3} />
                <small>{problem.ai_mode === 'simulation'
                  ? 'Checks the final expression only. Free-form reasoning and handwriting are not evaluated in simulation.'
                  : 'Enter your answer or use the handwriting workspace below.'}</small>
                <button type="button" className="academic-primary" disabled={submitting || !textAnswer.trim()}
                  onClick={() => onSubmitWritten(problem)}><Send size={15} /> Submit typed answer</button>
              </label>
              <div hidden={problem.ai_mode === 'simulation'}>
              <p className="answer-instruction">Write naturally as you would on paper, or upload a photograph of your derivation. The AI mentor evaluates mathematical logic rather than typography.</p>
              <div
                className={`vision-capability ${visionOCRAvailable === true ? 'is-ready' : visionOCRAvailable === false ? 'is-unavailable' : 'is-checking'}`}
                role="status"
                aria-live="polite"
              >
                {visionOCRAvailable === true ? (
                  <><CheckCircle2 size={15} /><span><strong>Vision OCR ready</strong><small>Handwriting will be transcribed before DeepSeek grading.</small></span></>
                ) : visionOCRAvailable === false ? (
                  <><AlertCircle size={15} /><span><strong>Vision OCR not configured</strong><small>Configure a dedicated vision provider to enable photo and handwritten review.</small></span></>
                ) : (
                  <><Loader2 className="animate-spin" size={15} /><span><strong>Checking vision OCR</strong><small>Confirming the handwriting transcription service.</small></span></>
                )}
              </div>

              <div className="drawing-paper">
                {selectedImage ? (
                  <div className="uploaded-work">
                    <Image src={selectedImage} alt="Uploaded mathematical work" width={760} height={520} unoptimized />
                    <button type="button" onClick={() => onRemoveImage(problem.id)} aria-label="Remove uploaded image"><X size={15} /></button>
                  </div>
                ) : (
                  <SignatureCanvas
                    ref={(instance) => onSignatureRef(problem.id, instance)}
                    penColor="#172033"
                    canvasProps={{
                      className: 'workspace-signature-canvas',
                      style: { width: '100%', height: '360px' },
                    }}
                  />
                )}

                {submitting && (
                  <div className="audit-overlay" role="status" aria-live="polite">
                    <Loader2 className="animate-spin" size={28} />
                    <strong>AI mentor is reviewing your reasoning</strong>
                    <span>This operation can take up to two minutes.</span>
                  </div>
                )}
              </div>

              <div className="written-actions">
                <button type="button" onClick={() => onSubmitWritten(problem)} disabled={submitting || visionOCRAvailable !== true} className="academic-primary">
                  <Send size={15} /> {selectedImage ? 'Submit uploaded work' : 'Submit handwritten answer'}
                </button>
                <div>
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    ref={(element) => onCameraInputRef(problem.id, element)}
                    onChange={(event) => onFileChange(event, problem.id)}
                    className="sr-only"
                  />
                  <button type="button" onClick={() => onOpenCamera(problem.id)} disabled={submitting || visionOCRAvailable !== true} aria-label="Take a photo">
                    <Camera size={18} /> <span>Camera</span>
                  </button>
                  <input
                    type="file"
                    accept="image/*"
                    ref={(element) => onFileInputRef(problem.id, element)}
                    onChange={(event) => onFileChange(event, problem.id)}
                    className="sr-only"
                  />
                  <button type="button" onClick={() => onOpenFilePicker(problem.id)} disabled={submitting || visionOCRAvailable !== true} aria-label="Select an image from files">
                    <FolderOpen size={18} /> <span>Files</span>
                  </button>
                </div>
              </div>
              </div>
            </section>
          )}

          {result && (
            <section className={`mentor-review workspace-review ${result.is_correct ? 'review-passed' : 'review-revise'}`} aria-label="Mentor review">
              <header>
                {result.is_correct ? <CheckCircle2 size={22} /> : <AlertCircle size={22} />}
                <div><small>MENTOR REVIEW · {problem.id}</small><h3>{result.is_correct ? 'Reasoning accepted' : 'Revision recommended'}</h3></div>
                <div className="review-score"><strong>{result.logic_alignment_score}</strong><span>/100</span></div>
              </header>
              <div className="review-score-track"><span style={{ width: `${result.logic_alignment_score}%` }} /></div>
              <div className="review-grid">
                {result.error_analysis && <div><small>Error analysis</small><div>{renderMathContent(result.error_analysis)}</div></div>}
                {result.tutor_feedback && <div><small>Supervisor&apos;s advice</small><div>{renderMathContent(result.tutor_feedback)}</div></div>}
                {result.next_hint && <div className="review-next-step"><small><Lightbulb size={12} /> Next-step guidance</small><div>{renderMathContent(result.next_hint)}</div></div>}
                <div className="course-citations">
                  <small>Course references · {result.retrieval_method || 'not recorded'}</small>
                  {result.citations?.length ? result.citations.map(citation => (
                    <button type="button" key={citation.citation_id} onClick={() => void openSource(citation)}>
                      <BookOpenText size={14} /> [{citation.citation_id}] {citation.title} · §{citation.section}
                    </button>
                  )) : <p>No supporting course reference was attached to this feedback.</p>}
                  {!!result.citations?.length && <p>References are available; support for each teaching claim has not been independently verified.</p>}
                  {result.progress_recorded && <p>Learning record saved by the server.</p>}
                  {sourceError && <p role="alert">{sourceError}</p>}
                </div>
                {result.ocr_text && <div><small><Camera size={12} /> {result.ai_mode === 'simulation' ? 'Submitted answer' : 'OCR transcription'}</small><div className="ocr-copy">{renderMathContent(result.ocr_text)}</div></div>}
              </div>
            </section>
          )}

          <footer className="problem-paper-footer">
            <div className="difficulty-bars" aria-label={`Difficulty level ${problem.difficulty} of 5`}>
              {[0, 1, 2, 3, 4].map((value) => <span key={value} className={value < Number(problem.difficulty) ? 'is-filled' : ''} />)}
            </div>
            <span>Calculus Atelier · Structured Exercise Folio</span>
          </footer>
        </article>
      ) : (
        <div className="workspace-empty-state">
          <span className="empty-formula">∫</span>
          <div className="workspace-empty-seal"><BookOpenText size={28} /></div>
          <p className="academic-kicker">EXERCISE FOLIO · AWAITING INQUIRY</p>
          <h3>Your mathematical workspace is ready.</h3>
          <p>Choose a curriculum domain and study protocol in the configuration panel, then generate a validated exercise.</p>
          <button type="button" onClick={onGenerate} disabled={generating} className="academic-primary">
            {generating ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
            {generating ? 'Preparing exercise…' : 'Generate first problem'}
          </button>
          <div className="empty-workflow" aria-label="Generation workflow">
            <span><SlidersHorizontal size={13} /> Configure</span><i /><span><Sparkles size={13} /> Generate</span><i /><span><CheckCircle2 size={13} /> Validate</span>
          </div>
        </div>
      )}
      {source && createPortal(
        <dialog ref={sourceDialog} className="source-drawer" aria-label="Course source" onCancel={() => setSource(null)}>
          <button type="button" onClick={() => setSource(null)} aria-label="Close course source"><X size={18} /></button>
          <p className="academic-kicker">COURSE EVIDENCE · {source.citation_id}</p>
          <h3>{source.title}</h3>
          <p>{source.source_title} · §{source.section} · Version {source.source_version}</p>
          <div className="source-excerpt">{renderMathContent(source.text)}</div>
          <small>{source.provenance}</small>
        </dialog>, document.body,
      )}
    </section>
  );
}
