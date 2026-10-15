"use client";
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, BookOpen, Check, ChevronDown, Download, FileCheck2, FileText, History, LoaderCircle, Microscope, Plus, ScanSearch, Square, X } from 'lucide-react';
import { usePharmaDeep } from '@/hooks/usePharmaDeep';
import { api } from '@/lib/api';
import { saveDownload } from '@/lib/interpolationDisplay';
import { progressiveText } from '@/lib/progressiveText';
import { isPrivateChat } from '@/lib/questionDrafts';
import { DEEP_TYPES, DEEP_STAGES, deepActive, deepSourceMethod, deepSources, takeDeepDraft, type DeepCoverage, type DeepJob, type DeepOptions, type DeepPlan, type DeepReport, type DeepType } from '@/lib/pharmaDeep';
import PharmaAnswer from './PharmaAnswer';

const PATH = '/analyst-workspace/pharma/deep';
const EXAMPLES = [
    ['Head-to-head', 'Compare tirzepatide and semaglutide in randomized head-to-head trials, including SURPASS-2 and SURMOUNT-5. Align populations, primary outcomes and safety evidence.'],
    ['Drug profile', 'Build an evidence-backed profile of Reblozyl: approvals, Phase 3 results, labeling, safety and patent listings. Separate established findings from unknowns.'],
    ['Generic entry', 'Investigate generic apixaban: FDA application actions, Orange Book patents and exclusivity, and official company or SEC statements. What remains unknown about US entry?'],
    ['Company pipeline', 'Review Pfizer’s obesity pipeline using current trial records, official announcements and SEC filings. Distinguish active programs from discontinued ones.'],
];
function date(value: string) { return new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); }
function statusLabel(status: string) { return ({ draft: 'Plan ready', queued: 'Queued', running: 'In progress', cancel_requested: 'Stopping', completed: 'Complete', partial: 'Coverage gaps', cancelled: 'Stopped', failed: 'Interrupted' }[status] || status); }

function PlanEditor({ job, options, busy, onStart }: { job: DeepJob; options: DeepOptions; busy: boolean; onStart: (plan: DeepPlan) => void }) {
    const [plan, setPlan] = useState(job.plan), [subjects, setSubjects] = useState(job.plan.subjects.join('\n'));
    const valid = subjects.trim() && plan.topics.length > 0 && subjects.split('\n').filter(s => s.trim()).length <= 3;
    return <section className="pd-plan" aria-label="Edit research plan"><div className="pd-section-heading"><div><span className="pd-kicker">Research plan</span><h2>Review the scope</h2></div><span className="pd-status"><FileCheck2 size={14} />Ready to edit</span></div>
        <div className="pd-scope"><label>Question type<select value={plan.question_type} onChange={event => { const kind = event.target.value as DeepType; setPlan({ ...plan, question_type: kind, topics: options.checklists[kind] }); }}>{Object.entries(DEEP_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
            <label className="pd-subjects">Medicines, companies or study IDs <span>One per line · up to three</span><textarea rows={3} maxLength={365} value={subjects} onChange={event => setSubjects(event.target.value)} /></label>
            <label>Condition or population <span>Optional</span><input value={plan.condition || ''} maxLength={160} onChange={event => setPlan({ ...plan, condition: event.target.value || null })} placeholder="e.g. myelodysplastic syndromes" /></label>
            <label>Research depth<select value={plan.max_rounds} onChange={event => setPlan({ ...plan, max_rounds: Number(event.target.value) })}><option value={1}>One round</option><option value={2}>Up to two rounds</option><option value={3}>Up to three rounds</option></select></label><label>Trial phase<select value={plan.phase || ''} onChange={event => setPlan({ ...plan, phase: (event.target.value || null) as DeepPlan['phase'] })}><option value="">All phases</option>{[1, 2, 3, 4].map(phase => <option key={phase} value={`PHASE${phase}`}>Phase {phase}</option>)}</select></label></div>
        <fieldset className="pd-checklist"><legend>I will check</legend>{options.topics.map(topic => <label key={topic.id}><input type="checkbox" checked={plan.topics.includes(topic.id)} onChange={event => setPlan({ ...plan, topics: event.target.checked ? [...plan.topics, topic.id] : plan.topics.filter(t => t !== topic.id) })} /><span><strong>{topic.label}</strong><small>{topic.description}</small></span></label>)}</fieldset>
        <footer className="pd-plan-footer"><p>Up to {plan.max_rounds} research rounds. The report stays in your history and can finish while you are away.</p><button className="pd-primary" disabled={!valid || busy} onClick={() => onStart({ ...plan, subjects: subjects.split('\n').map(s => s.trim()).filter(Boolean) })}>{busy ? <LoaderCircle size={16} className="pi-spinning" /> : <ScanSearch size={16} />}Start research</button></footer>
    </section>;
}

function Coverage({ rows }: { rows: DeepCoverage[] }) {
    if (!rows.length) return null;
    return <section className="pd-coverage" aria-label="Research coverage"><h2>Source coverage</h2><ul>{rows.map(row => <li key={row.topic} data-state={row.status}><span>{row.status === 'covered' ? <Check size={14} /> : <span className="pd-coverage-dot" />}<strong>{row.label}</strong></span><span>{row.status === 'covered' ? `${row.sources} source${row.sources === 1 ? '' : 's'}` : row.status === 'partial' ? 'Excerpts only' : row.status === 'unavailable' ? 'Unavailable' : 'Not established'}</span></li>)}</ul><p>Coverage reflects this retrieved sample, not every available source.</p></section>;
}

function Activity({ job, running }: { job: DeepJob; running: boolean }) {
    const activeIndex = DEEP_STAGES.findIndex(s => s.id === job.stage);
    const latest = new Map<string, typeof job.activity[number]>();
    for (const event of job.activity) latest.set(event.task || `${event.round}:${event.stage}:${event.title}`, event);
    const recent = Array.from(latest.values()).slice(-8), metrics = job.metrics || {};
    const done = (stage: string) => stage === 'plan' ? job.status !== 'draft' : stage === 'deliver' ? !!job.report : job.activity.some(event => event.stage === stage && event.status !== 'running' && (stage !== 'write' || event.detail.startsWith('Draft saved')) && (stage !== 'verify' || event.title === 'Verification complete'));
    return <section className="pd-activity" aria-label="Research progress" aria-busy={running}>
        <ol className="pd-stages">{DEEP_STAGES.map((stage, index) => <li key={stage.id} data-active={stage.id === job.stage && job.status !== 'queued'} data-done={done(stage.id)} aria-current={stage.id === job.stage && job.status !== 'queued' ? 'step' : undefined}><span>{done(stage.id) ? <Check size={12} /> : index + 1}</span>{stage.label}</li>)}</ol>
        <div className="pd-activity-heading"><h2>{job.status === 'queued' ? 'Waiting for a research slot' : job.status === 'cancel_requested' ? 'Stopping research' : running ? (DEEP_STAGES[activeIndex]?.label || 'Research') + (metrics.round ? ` · round ${metrics.round} of ${job.plan.max_rounds}` : '') : 'Research activity'}</h2>{running && <LoaderCircle size={16} className="pi-spinning" />}</div>
        <dl className="pd-metrics"><div><dt>Source lookups</dt><dd>{metrics.search_count || 0}</dd></div><div><dt>Documents read</dt><dd>{metrics.documents_read || 0}</dd></div><div><dt>Verified findings</dt><dd>{metrics.verified_claims || 0}</dd></div></dl>
        {recent.length ? <ul className="pd-task-list" aria-live="polite" aria-relevant="additions text">{recent.map(event => <li key={event.id} data-state={event.status}>{event.status === 'running' && running && event.stage === job.stage ? <span className="pd-task-dot" /> : event.status === 'available' || event.status === 'complete' ? <Check size={13} /> : <span aria-hidden="true">—</span>}<div><strong>{event.title}</strong><p>{event.detail}</p></div></li>)}</ul> : <p className="pd-wait">Your plan is saved. Research begins when a slot is available.</p>}
        {job.activity.length > 8 && <details className="pd-audit"><summary>All activity<ChevronDown size={13} /></summary><ol>{job.activity.map(event => <li key={event.id}><span>{new Date(event.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · round {event.round || 1}</span><strong>{event.title}</strong><p>{event.detail}</p></li>)}</ol></details>}
        {job.outline?.length ? <details className="pd-outline"><summary>Report outline<ChevronDown size={14} /></summary><ol>{job.outline.map(section => <li key={section.heading}>{section.heading}</li>)}</ol></details> : null}
    </section>;
}

function EvidenceLedger({ report }: { report: DeepReport }) {
    const [source, setSource] = useState('all'), [method, setMethod] = useState('all');
    const quotes = report.quotes.filter(q => (source === 'all' || String(q.source) === source) && (method === 'all' || q.method === method));
    return <details className="pd-ledger"><summary><BookOpen size={16} /><span>Evidence ledger <small>{report.quotes.length} saved passages and source fields</small></span><ChevronDown size={16} /></summary>
        <div className="pd-ledger-controls"><label>Source<select value={source} onChange={event => setSource(event.target.value)}><option value="all">All sources</option>{report.sources.map(s => <option key={s.id} value={s.id}>[{s.id}] {s.title}</option>)}</select></label><label>Evidence type<select value={method} onChange={event => setMethod(event.target.value)}><option value="all">All evidence</option>{Array.from(new Set(report.quotes.map(q => q.method))).map(m => <option key={m} value={m}>{deepSourceMethod(m)}</option>)}</select></label></div>
        <ol className="pd-passages">{quotes.map(quote => { const ref = report.sources.find(s => s.id === quote.source); return <li key={quote.id}><div><span>{deepSourceMethod(quote.method)}</span><code>{quote.id}</code></div><blockquote>{quote.text}</blockquote>{ref && <a href={ref.url} target="_blank" rel="noopener noreferrer">[{ref.id}] {ref.title}<ArrowUpRight size={13} /></a>}</li>; })}</ol>{!quotes.length && <p>No passages match these filters.</p>}
    </details>;
}

function Report({ job }: { job: DeepJob }) {
    const report = job.report!;
    const [content, setContent] = useState(''), [revealing, setRevealing] = useState(true), [download, setDownload] = useState(''), [error, setError] = useState('');
    const reveal = useRef<ReturnType<typeof progressiveText> | null>(null);
    useEffect(() => {
        const controller = new AbortController(), display = progressiveText(setContent, controller.signal); reveal.current = display;
        display.append(report.markdown); void display.finish().then(() => { if (!controller.signal.aborted) setRevealing(false); });
        return () => { controller.abort(); display.cancel(); };
    }, [report.markdown]);
    const exportReport = async (format: 'docx' | 'pdf' | 'xlsx') => {
        if (download) return; setDownload(format); setError('');
        try { const response = await api.response(`/api/v1/pharma/deep/${job.id}/download/${format}`); saveDownload(await response.blob(), `corten-pharma-${job.id}.${format}`); }
        catch (failure) { setError(failure instanceof Error ? failure.message : 'The download could not be created. Please retry.'); }
        finally { setDownload(''); }
    };
    return <div className="pd-delivered"><div className="pd-report-toolbar"><span><FileCheck2 size={15} />Saved {date(report.generated_at)}</span><div>{(['docx', 'pdf', 'xlsx'] as const).map(format => <button className="pi-button" key={format} disabled={!!download} onClick={() => void exportReport(format)}>{download === format ? <LoaderCircle size={14} className="pi-spinning" /> : <Download size={14} />}{format === 'docx' ? 'Word' : format === 'xlsx' ? 'Excel evidence' : 'PDF'}</button>)}</div></div>
        {error && <p className="pd-error" role="alert">{error}</p>}
        {revealing && <button className="pd-show-full" onClick={() => reveal.current?.showAll()}>Show full report</button>}
        <div className="pd-report-body"><PharmaAnswer content={content} sources={deepSources(report.sources)} streaming={revealing} /></div>
        <EvidenceLedger report={report} />
        {!!report.search_coverage?.length && <details className="pd-source-register"><summary>What was checked<span>{report.search_coverage.length} lookups<ChevronDown size={14} /></span></summary><ol>{report.search_coverage.map((search, index) => <li key={index}><strong>{report.coverage.find(c => c.topic === search.topic)?.label} · {search.query}</strong><p>{search.status === 'available' ? 'Evidence retrieved' : search.status === 'empty' ? 'No matches in this search' : 'Source unavailable'}. {search.coverage}</p></li>)}</ol></details>}
        <details className="pd-source-register"><summary>Source register <span>{report.sources.length}<ChevronDown size={14} /></span></summary><ol>{report.sources.map(source => <li key={source.id}><a href={source.url} target="_blank" rel="noopener noreferrer"><span>[{source.id}] {source.title}</span><ArrowUpRight size={14} /></a><p>{deepSourceMethod(source.read_status)} · Retrieved {date(source.retrieved_at)}{source.date ? ` · ${source.date_meaning || 'Source date'}: ${source.date}` : ''}</p></li>)}</ol></details>
        <details className="pd-completed-activity"><summary>Research activity<ChevronDown size={14} /></summary><Activity job={job} running={false} /></details>
    </div>;
}

function StopDialog({ onStop, onClose }: { onStop: () => void; onClose: () => void }) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => { ref.current?.showModal(); }, []);
    return <dialog ref={ref} className="pd-stop-dialog" aria-labelledby="pd-stop-title" onCancel={onClose}><button className="pd-dialog-close" aria-label="Close stop confirmation" onClick={onClose}><X size={18} /></button><h2 id="pd-stop-title">Stop this research?</h2><p>Your plan and collected source evidence will remain available.</p><div><button className="pi-button" onClick={onClose} autoFocus>Keep researching</button><button className="pd-primary" onClick={onStop}>Stop research</button></div></dialog>;
}

export default function PharmaDeepResearch() {
    const search = useSearchParams(), router = useRouter(), chat = usePharmaDeep(search.get('id') || '');
    const [query, setQuery] = useState(''), [historyOpen, setHistoryOpen] = useState(false), [stopping, setStopping] = useState(false);
    const [allowSaved, setAllowSaved] = useState(false);
    const textarea = useRef<HTMLTextAreaElement>(null), job = chat.job, running = deepActive(job);
    useEffect(() => { const timer = setTimeout(() => setQuery(takeDeepDraft()), 0); return () => clearTimeout(timer); }, []);
    const prepare = async () => { if (!query.trim() || chat.operation) return; const next = await chat.prepare(query.trim(), allowSaved); if (next) router.replace(`${PATH}?id=${next.id}`); };
    return <section className="pr-page pd-page" aria-label="Pharma deep research"><header className="pi-detail-nav"><Link className="pi-button" href="/analyst-workspace?tool=pharma"><ArrowLeft size={14} />Pharma intelligence</Link><div><button className="pi-button" aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}><History size={14} />Research history</button><button className="pi-button" onClick={() => { router.push(PATH); setQuery(''); setAllowSaved(false); textarea.current?.focus(); }}><Plus size={14} />New research</button></div></header>
        <div className="pd-shell"><div className="pd-main"><header className="pd-heading"><span className="pd-kicker"><ScanSearch size={16} />Deep research</span><h1>{job ? job.query : 'Pharma deep research'}</h1>{job ? <div className="pd-meta"><span className={`pd-job-status pd-job-${job.status}`}>{statusLabel(job.status)}</span><span>{DEEP_TYPES[job.plan.question_type]}</span><span>{date(job.created_at)}</span></div> : <p>Review and edit the source checklist before research begins.</p>}</header>
        {historyOpen && <section className="pd-history" aria-label="Research history"><div className="pd-section-heading"><h2>Research history</h2><button aria-label="Close research history" onClick={() => setHistoryOpen(false)}><X size={16} /></button></div>{chat.history.length ? <ul>{chat.history.map(item => <li key={item.id}><Link href={`${PATH}?id=${item.id}`} onClick={() => setHistoryOpen(false)}><strong>{item.query}</strong><span>{statusLabel(item.status)} · {date(item.created_at)}</span><ArrowUpRight size={14} /></Link></li>)}</ul> : <p>Your research plans and reports will appear here.</p>}</section>}
        {chat.error && <div className="pd-error" role="alert"><p>{chat.error}</p>{job && <button className="pi-button" onClick={chat.reload}>Reload progress</button>}</div>}
        {chat.loading && !job && <div className="pd-loading" role="status"><LoaderCircle size={20} className="pi-spinning" />Loading saved research</div>}
        {!job && !chat.loading && <><form className="pd-question" onSubmit={event => { event.preventDefault(); void prepare(); }}><label htmlFor="pd-question">Research question</label><textarea id="pd-question" ref={textarea} value={query} maxLength={4000} rows={5} onChange={event => setQuery(event.target.value)} placeholder="What should we investigate? Name the medicines, company or studies and the decision you need to make." /><footer><Link href="/analyst-workspace/pharma/research">Standard research<ArrowUpRight size={13} /></Link><button className="pd-primary" disabled={!query.trim() || !!chat.operation || !chat.options || (isPrivateChat() && !allowSaved)}>{chat.operation === 'plan' ? <LoaderCircle size={16} className="pi-spinning" /> : <ScanSearch size={16} />}{chat.operation === 'plan' ? 'Preparing plan' : 'Deep research'}</button></footer>{isPrivateChat() && <div className="pd-private-note"><p>Deep research creates a report saved to your account. Your other private chats stay private.</p><label><input type="checkbox" checked={allowSaved} onChange={event => setAllowSaved(event.target.checked)} />Save this research to my account</label></div>}</form>
            {chat.operation === 'plan' ? <section className="pd-planning" role="status"><span className="pd-task-dot" /><div><h2>Preparing your research plan</h2><p>Identifying the question type, named subjects and source checklist.</p></div></section> : <section className="pd-examples" aria-label="Example research questions">{EXAMPLES.map(([label, value]) => <button key={label} onClick={() => { setQuery(value); textarea.current?.focus(); }}><span>{label}</span><p>{value}</p><ArrowUpRight size={15} /></button>)}</section>}</>}
        {job?.status === 'draft' && chat.options && <PlanEditor key={job.id} job={job} options={chat.options} busy={!!chat.operation} onStart={plan => void chat.start(plan)} />}
        {job && running && <><Activity job={job} running /><p className="pd-background-note">You can leave this page. Research continues and the report stays in your history.</p><button className="pi-button pd-stop" disabled={job.status === 'cancel_requested' || !!chat.operation} onClick={() => setStopping(true)}><Square size={12} />{job.status === 'cancel_requested' ? 'Stopping research' : 'Stop research'}</button></>}
        {job?.status === 'failed' && <section className="pd-interrupted"><h2>Research interrupted</h2><p>{job.error || 'The plan and collected evidence are saved.'}</p>{job.retryable !== false && <button className="pi-button" disabled={!!chat.operation} onClick={() => void chat.retry()}>Retry research</button>}<button className="pi-button" onClick={() => { setQuery(job.query); router.push(PATH); }}>Create a new plan</button></section>}
        {job?.status === 'cancelled' && !job.report && <p className="pd-interrupted">This research was stopped. Your plan remains in research history.</p>}
        {job?.report && <Report key={job.id} job={job} />}
        </div>{job && (job.coverage?.length || job.report?.coverage.length) ? <aside className="pd-aside"><Coverage rows={job.report?.coverage || job.coverage || []} /></aside> : null}</div>
        {stopping && <StopDialog onClose={() => setStopping(false)} onStop={() => { setStopping(false); void chat.cancel(); }} />}
    </section>;
}
