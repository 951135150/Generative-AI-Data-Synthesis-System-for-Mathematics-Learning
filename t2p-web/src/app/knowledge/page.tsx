'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { ArrowLeft, BookOpenText, FileUp, Loader2, Search, ShieldCheck } from 'lucide-react';
import { useUser } from '@/context/UserContext';
import { api, getApiErrorMessage } from '@/lib/api';

interface Passage {
  id: string; title: string; text: string; topic: string; section: string;
  source_id?: string; source_title?: string; source_version?: string;
}
interface Source {
  source_id: string; title: string; version: string; status?: string;
  source_hash?: string; chunk_count?: number; provenance: string; license: string;
}
interface CourseDocument {
  source_id: string; title: string; version: string; status: string; chunks: Passage[];
}
interface ImportForm {
  source_id: string; title: string; version: string; topic: string;
  provenance: string; license_name: string; filename: string; content: string;
  encoding: 'text' | 'base64'; publish: boolean; review_confirmed: boolean;
}
interface Preview { document: CourseDocument; existing_hash: string | null; formSnapshot: string }

const emptyForm: ImportForm = {
  source_id: '', title: '', version: '1', topic: '', provenance: '', license_name: '',
  filename: 'notes.md', content: '', encoding: 'text', publish: false, review_confirmed: false,
};

function PassageCard({ passage }: { passage: Passage }) {
  return <article className="library-passage">
    <p className="academic-kicker">{passage.topic} · §{passage.section}</p>
    <h3>{passage.title}</h3>
    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{passage.text}</ReactMarkdown>
    {passage.source_title && <small>{passage.source_title} · Version {passage.source_version}</small>}
  </article>;
}

export default function CourseLibrary() {
  const { authenticated, role, userId, authReady } = useUser();
  const admin = authenticated && role === 'admin';
  const [sources, setSources] = useState<Source[]>([]);
  const [chunks, setChunks] = useState<Passage[]>([]);
  const [managed, setManaged] = useState<Source[]>([]);
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [results, setResults] = useState<Passage[] | null>(null);
  const [selectedSource, setSelectedSource] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState<ImportForm>(emptyForm);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [inspected, setInspected] = useState<CourseDocument | null>(null);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);

  const fetchCatalog = useCallback(async () => {
    try {
      const response = await api.get('/knowledge/catalog');
      setSources(response.data.sources);
      setChunks(response.data.chunks);
    } catch (failure) {
      setError(getApiErrorMessage(failure, 'Unable to load the course catalog.'));
    }
  }, []);
  const fetchManaged = useCallback(async () => {
    if (!admin) return;
    try {
      const response = await api.get('/knowledge/manage/sources');
      setManaged(response.data.sources);
    } catch (failure) {
      setError(getApiErrorMessage(failure, 'Unable to load administration records.'));
    }
  }, [admin]);
  useEffect(() => { void fetchCatalog(); }, [fetchCatalog]);
  useEffect(() => { void fetchManaged(); }, [fetchManaged]);

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) { setResults(null); return; }
    setLoading(true); setError('');
    try {
      const response = await api.get('/knowledge/search', { params: { query: query.trim(), topic: topic || undefined } });
      setResults(response.data.data.evidence || []);
      if (response.data.data.status === 'unavailable') setError('Course retrieval is temporarily unavailable. Browse the notes below or check the local model.');
    } catch (failure) { setError(getApiErrorMessage(failure, 'Course search failed.')); }
    finally { setLoading(false); }
  };
  const updateForm = <K extends keyof ImportForm>(key: K, value: ImportForm[K]) => {
    setForm(current => ({ ...current, [key]: value }));
    setPreview(null);
    setNotice('');
  };
  const readFile = async (file?: File) => {
    if (!file) return;
    if (file.size > 5_000_000) { setError('Choose a course file smaller than 5 MB.'); return; }
    try {
      const isPDF = file.name.toLowerCase().endsWith('.pdf');
      let content: string;
      if (isPDF) {
        content = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
          reader.onerror = () => reject(new Error('The file could not be read.'));
          reader.readAsDataURL(file);
        });
      } else content = await file.text();
      setForm(current => ({ ...current, filename: file.name, content, encoding: isPDF ? 'base64' : 'text' }));
      setPreview(null); setError('');
    } catch { setError('The file could not be read. Try a UTF-8 Markdown file.'); }
  };
  const previewImport = async (event: React.FormEvent) => {
    event.preventDefault(); setLoading(true); setError(''); setNotice('');
    try {
      const response = await api.post('/knowledge/manage/preview', form);
      setPreview({ document: response.data.document, existing_hash: response.data.existing_hash, formSnapshot: JSON.stringify(form) });
    } catch (failure) { setError(getApiErrorMessage(failure, 'Unable to preview this source.')); }
    finally { setLoading(false); }
  };
  const saveImport = async () => {
    if (!preview || preview.formSnapshot !== JSON.stringify(form)) return;
    setLoading(true); setError('');
    try {
      await api.post('/knowledge/manage/save', { ...form, expected_hash: preview.existing_hash });
      setNotice(form.publish ? 'Source published. It is available to new retrieval requests.' : 'Draft saved. Learners cannot retrieve it until publication.');
      setPreview(null); setResults(null);
      await Promise.all([fetchCatalog(), fetchManaged()]);
    } catch (failure) { setError(getApiErrorMessage(failure, 'Unable to save this source.')); }
    finally { setLoading(false); }
  };
  const inspect = async (source: Source) => {
    setLoading(true); setError(''); setReviewConfirmed(false);
    try {
      const response = await api.get(`/knowledge/manage/sources/${encodeURIComponent(source.source_id)}`);
      setInspected(response.data.document);
    } catch (failure) { setError(getApiErrorMessage(failure, 'Unable to open the source.')); }
    finally { setLoading(false); }
  };
  const changeStatus = async (source: Source, status: 'published' | 'withdrawn') => {
    setLoading(true); setError('');
    try {
      await api.post(`/knowledge/manage/sources/${encodeURIComponent(source.source_id)}/status`, {
        status, expected_hash: source.source_hash, review_confirmed: reviewConfirmed,
      });
      setNotice(status === 'published' ? 'Source published.' : 'Source withdrawn. Previous versions remain archived.');
      setReviewConfirmed(false); setInspected(null); setResults(null);
      await Promise.all([fetchCatalog(), fetchManaged()]);
    } catch (failure) { setError(getApiErrorMessage(failure, 'Unable to change publication status.')); }
    finally { setLoading(false); }
  };

  const topics = Array.from(new Set(chunks.map(chunk => chunk.topic))).sort();
  const displayed = (results || chunks).filter(chunk => (!topic || chunk.topic === topic) && (!selectedSource || chunk.source_id === selectedSource));
  return <div className="workspace-app">
    <div className="academic-rule" />
    <header className="workspace-topbar library-topbar">
      <Link href="/" className="workspace-brand"><BookOpenText size={24} /><strong>Calculus Atelier</strong></Link>
      <nav aria-label="Course library navigation"><Link href="/">Problem Studio</Link><Link href="/dashboard">Progress</Link><span aria-current="page">Course Library</span></nav>
      <span>{authReady && authenticated ? userId : 'Course reference collection'}</span>
    </header>
    <main className="workspace-main course-library">
      <section className="workspace-intro"><div>
        <p className="academic-kicker">COURSE REFERENCE COLLECTION</p>
        <h1>Learn from <em>traceable sources.</em></h1>
        <span>Browse published course notes, inspect the mathematics, and find the references behind your mentor feedback.</span>
      </div><div className="library-count"><strong>{chunks.length}</strong><span>knowledge units · {sources.length} sources</span></div></section>
      {error && <p role="alert" className="library-alert">{error}</p>}
      {notice && <p role="status" className="library-notice">{notice}</p>}
      <form className="library-search" onSubmit={search}>
        <label>Search course notes<input value={query} onChange={event => setQuery(event.target.value)} placeholder="e.g. chain rule or 换元积分" maxLength={500} /></label>
        <label>Topic<select value={topic} onChange={event => { setTopic(event.target.value); setResults(null); }}><option value="">All topics</option>{topics.map(item => <option key={item}>{item}</option>)}</select></label>
        <button type="submit" className="academic-primary" disabled={loading}><Search size={16} /> Search</button>
        {results && <button type="button" onClick={() => { setResults(null); setQuery(''); }}>Clear search</button>}
      </form>
      <div className="library-grid">
        <aside className="laboratory-panel library-sources"><p className="academic-kicker">REGISTERED SOURCES</p><h2>Course collection</h2>
          <button type="button" aria-pressed={!selectedSource} onClick={() => setSelectedSource('')}>All published notes</button>
          {sources.map(source => <button type="button" key={source.source_id} aria-pressed={selectedSource === source.source_id} onClick={() => setSelectedSource(source.source_id)}>
            <strong>{source.title}</strong><small>Version {source.version} · {source.license}</small><span>{source.provenance}</span>
          </button>)}
          <p>Only published material appears here. Original project notes are not externally certified textbook excerpts.</p>
        </aside>
        <section aria-label="Course passages" className="library-passages">
          {loading && <p role="status"><Loader2 size={16} className="animate-spin" /> Working with the local course collection…</p>}
          {!displayed.length && !loading && <p className="library-empty">No matching published course passage was found. Try another term or topic.</p>}
          {displayed.map(passage => <PassageCard key={passage.id} passage={passage} />)}
        </section>
      </div>
      {admin ? <section className="library-management" aria-label="Course administration">
        <p className="academic-kicker"><ShieldCheck size={14} /> COURSE ADMINISTRATION</p><h2>Review before publication.</h2>
        <p>Upload permitted material, inspect every extracted unit, then save a draft or publish. Changing content requires a new version.</p>
        <form className="library-import" onSubmit={previewImport}>
          {([
            ['source_id', 'Source ID'], ['title', 'Source title'], ['version', 'Version'], ['topic', 'Curriculum topic'],
            ['provenance', 'Author and provenance'], ['license_name', 'Permission or license'],
          ] as const).map(([key, label]) => <label key={key}>{label}<input required value={form[key]} onChange={event => updateForm(key, event.target.value)} /></label>)}
          <label className="library-wide">Course file · Markdown, text, JSON or text-readable PDF<input type="file" accept=".md,.txt,.json,.pdf" onChange={event => void readFile(event.target.files?.[0])} /></label>
          {form.encoding === 'text' && <label className="library-wide">Source text<textarea rows={6} required value={form.content} onChange={event => updateForm('content', event.target.value)} placeholder="# Section title&#10;Your course notes and complete LaTeX formulas." /></label>}
          <label className="library-check"><input type="checkbox" checked={form.publish} onChange={event => updateForm('publish', event.target.checked)} /> Publish after preview</label>
          <label className="library-check"><input type="checkbox" checked={form.review_confirmed} onChange={event => updateForm('review_confirmed', event.target.checked)} /> I reviewed source rights, mathematics and extracted formulas.</label>
          <button type="submit" className="academic-primary" disabled={loading || (form.publish && !form.review_confirmed)}><FileUp size={16} /> Preview source</button>
        </form>
        {preview && <div className="library-preview" role="region" aria-label="Import preview"><h3>{preview.document.title} · {preview.document.chunks.length} units · {preview.document.status}</h3>
          {preview.document.chunks.map(passage => <PassageCard key={passage.id} passage={passage} />)}
          <button type="button" className="academic-primary" disabled={loading} onClick={() => void saveImport()}>{form.publish ? 'Save and publish source' : 'Save draft'}</button>
        </div>}
        <h3>Source publication register</h3>
        <div className="library-register">{managed.map(source => <div key={source.source_id}>
          <span><strong>{source.title}</strong><small>{source.source_id} · v{source.version} · {source.status} · {source.chunk_count} units</small></span>
          <button type="button" disabled={loading} onClick={() => void inspect(source)}>Review source</button>
          {source.status === 'published'
            ? <button type="button" disabled={loading} onClick={() => void changeStatus(source, 'withdrawn')}>Withdraw</button>
            : <button type="button" disabled={loading || !reviewConfirmed || inspected?.source_id !== source.source_id} onClick={() => void changeStatus(source, 'published')}>Publish reviewed source</button>}
        </div>)}</div>
        {inspected && <div className="library-preview" role="region" aria-label="Source review"><h3>{inspected.title} · Version {inspected.version}</h3>
          {inspected.chunks.map(passage => <PassageCard key={passage.id} passage={passage} />)}
          <label className="library-check"><input type="checkbox" checked={reviewConfirmed} onChange={event => setReviewConfirmed(event.target.checked)} /> I reviewed this source&apos;s rights, mathematics and extracted formulas.</label>
        </div>}
      </section> : <p className="library-access-note">Publishing is restricted to course administrators. {!authenticated && <Link href="/">Sign in through Problem Studio.</Link>}</p>}
      <Link href="/" className="library-back"><ArrowLeft size={15} /> Return to Problem Studio</Link>
    </main>
  </div>;
}
