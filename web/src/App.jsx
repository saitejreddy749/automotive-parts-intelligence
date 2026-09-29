import { useEffect, useState } from 'react'
import { post, request } from './api'

const NAV = [
  ['overview', 'Overview', '▦'],
  ['catalogues', 'Catalogues', '▤'],
  ['review', 'Match review', '◎'],
  ['fitment', 'Fitment lookup', '◇'],
  ['evaluations', 'Evaluations', '▥'],
]

const percent = value => `${Math.round((value || 0) * 100)}%`
const score = value => `${Math.round((value || 0) * 100)}%`

function Metric({ label, value, note, accent = false }) {
  return <div className={`metric ${accent ? 'metric-accent' : ''}`}>
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}</div>
    <div className="metric-note">{note}</div>
  </div>
}

function Panel({ title, kicker, action, children, className = '' }) {
  return <section className={`panel ${className}`}>
    <div className="panel-head"><div><div className="eyebrow">{kicker}</div><h2>{title}</h2></div>{action}</div>
    {children}
  </section>
}

function Empty({ title, detail }) {
  return <div className="empty"><span className="empty-mark">◇</span><strong>{title}</strong><p>{detail}</p></div>
}

function Source({ part, compact = false }) {
  return <div className={`source ${compact ? 'source-compact' : ''}`}>
    <div className="source-top"><span className="brand">{part.brand}</span><span className="sku">{part.supplier} · {part.sku}</span></div>
    <strong>{part.part_number}</strong><p>{part.description}</p>
    <div className="source-fit">{part.make} {part.model} · {part.year_start}–{part.year_end}{part.engine ? ` · ${part.engine}` : ' · engine unspecified'}</div>
  </div>
}

function Bar({ label, value }) {
  return <div className="bar-line"><div><span>{label}</span><strong>{percent(value)}</strong></div><div className="bar-track"><span style={{ width: percent(value) }} /></div></div>
}

function Overview({ overview, catalogues, evaluations, go }) {
  const latest = evaluations[0]
  return <>
    <div className="hero"><div>
      <span className="hero-pill"><span className="live-dot" /> DEMO WORKSPACE</span>
      <h1>From messy catalogues<br />to <em>traceable parts.</em></h1>
      <p>Standardise supplier records, review duplicate candidates, and check declared vehicle fitment with source evidence attached.</p>
      <button className="button button-light" onClick={() => go('review')}>Review matches <span>↗</span></button>
    </div><div className="hero-art" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="core">◎</span><span className="node node-a" /><span className="node node-b" /><span className="node node-c" /></div></div>
    <div className="metric-grid">
      <Metric label="Supplier records" value={overview.supplier_rows} note={`${overview.catalogues} catalogues imported`} />
      <Metric label="Canonical parts" value={overview.canonical_parts} note="Confirmed groups only" />
      <Metric label="Pending review" value={overview.pending} note="Candidate matches to inspect" accent />
      <Metric label="Labeled test pairs" value={overview.gold_pairs} note="Synthetic evaluation set" />
    </div>
    <div className="two-col">
      <Panel kicker="WORKFLOW" title="A decision you can inspect">
        <div className="steps">{[
          ['01', 'Import', 'Keep the original supplier CSV.'],
          ['02', 'Normalise', 'Clean names and part numbers.'],
          ['03', 'Suggest', 'Score likely duplicates.'],
          ['04', 'Confirm', 'A person approves each merge.'],
        ].map(([number, title, detail]) => <div className="step" key={number}><span>{number}</span><div><strong>{title}</strong><p>{detail}</p></div></div>)}</div>
      </Panel>
      <Panel kicker="LATEST EXPERIMENT" title="Matching quality" action={<button className="text-link" onClick={() => go('evaluations')}>View evaluations ↗</button>}>
        {latest ? <><div className="run-meta"><span>Threshold {latest.threshold.toFixed(2)}</span><span>{latest.model_version}</span></div>
          <Bar label="Precision" value={latest.precision} /><Bar label="Recall" value={latest.recall} /><Bar label="F1 score" value={latest.f1} />
          <p className="fine-print">Measured on {latest.label_count} curated, synthetic labeled pairs. These figures do not estimate real catalogue performance.</p></>
          : <Empty title="No run yet" detail="Run an evaluation against the labeled demo pairs." />}
      </Panel>
    </div>
    <Panel kicker="DATA LINEAGE" title="Imported sources" action={<button className="text-link" onClick={() => go('catalogues')}>Open catalogues ↗</button>}>
      <div className="table-wrap"><table><thead><tr><th>Catalogue</th><th>Rows</th><th>Rejected</th><th>Raw storage</th><th>SHA-256</th></tr></thead><tbody>
        {catalogues.map(c => <tr key={c.id}><td><strong>{c.filename}</strong></td><td>{c.rows}</td><td>{c.invalid}</td><td><span className="tag">{c.storage}</span></td><td className="mono">{c.sha256}…</td></tr>)}
      </tbody></table></div>
    </Panel>
  </>
}

function Catalogues({ catalogues, refresh, flash }) {
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [groups, setGroups] = useState([])
  const [selected, setSelected] = useState(null)
  const [similar, setSimilar] = useState([])
  useEffect(() => { request('/parts').then(setGroups).catch(error => flash(error.message, true)) }, [])
  async function upload(event) {
    event.preventDefault()
    const formElement = event.currentTarget
    const file = formElement.elements.file.files[0]
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData(); form.append('file', file)
      const result = await request('/catalogues', { method: 'POST', body: form })
      flash(`Imported ${result.accepted} rows and found ${result.new_proposals} new suggestions${result.invalid.length ? `; ${result.invalid.length} rows rejected` : ''}.`)
      formElement.reset()
      setGroups(await request('/parts'))
      await refresh()
    } catch (error) { flash(error.message, true) }
    finally { setBusy(false) }
  }
  async function search(event) {
    event.preventDefault()
    try { setGroups(await request(`/parts?q=${encodeURIComponent(query)}`)); setSelected(null) }
    catch (error) { flash(error.message, true) }
  }
  async function inspect(group) {
    setSelected(group)
    try { setSimilar(await request(`/parts/${group.sources[0].id}/similar`)) }
    catch (error) { flash(error.message, true) }
  }
  return <>
    <div className="page-title"><span className="eyebrow">01 / SOURCE DATA</span><h1>Catalogues</h1><p>Every result keeps its original supplier record. Add a CSV to generate new review candidates.</p></div>
    <div className="two-col wide-left">
      <Panel kicker="INVENTORY" title="Canonical part groups" action={<span className="counter">{groups.length} shown</span>}>
        <form className="search-row" onSubmit={search}><input aria-label="Search parts" placeholder="Search brand, number, SKU, description…" value={query} onChange={event => setQuery(event.target.value)} /><button className="button button-primary">Search</button></form>
        <div className="group-list">{groups.map(group => <button className={`group-row ${selected?.canonical_id === group.canonical_id ? 'selected' : ''}`} key={group.canonical_id} onClick={() => inspect(group)}>
          <div><strong>{group.sources[0].brand} <span>{group.sources[0].part_number}</span></strong><p>{group.sources[0].description}</p></div><span className="group-count">{group.source_count} source{group.source_count !== 1 ? 's' : ''} →</span>
        </button>)}{!groups.length && <Empty title="No parts found" detail="Try another search or import a supplier CSV." />}</div>
      </Panel>
      <div className="stack">
        <Panel kicker="IMPORT" title="Add supplier catalogue"><form onSubmit={upload} className="upload-form"><div className="upload-target"><span>⇧</span><strong>Select a CSV file</strong><small>UTF-8 · maximum 500 rows / 2 MB</small><input type="file" name="file" accept=".csv,text/csv" required /></div><button className="button button-primary" disabled={busy}>{busy ? 'Importing…' : 'Import catalogue'}</button></form><p className="fine-print">Required: supplier, sku, brand, part_number, description, category, make, model, year_start, year_end. Optional: engine.</p></Panel>
        <Panel kicker="EVIDENCE" title={selected ? `Group #${selected.canonical_id}` : 'Select a group'}>
          {selected ? <><div className="detail-sources">{selected.sources.map(part => <Source key={part.id} part={part} compact />)}</div><h3 className="mini-heading">Nearest records</h3>{similar.length ? similar.map(item => <div className="similar-row" key={item.part.id}><span>{item.part.brand} {item.part.part_number}</span><span>{score(item.similarity)} vector similarity</span></div>) : <p className="muted">No similar records from another supplier.</p>}</> : <p className="muted">Inspect source rows and vector-based neighbors for any part.</p>}
        </Panel>
      </div>
    </div>
    <Panel kicker="FILE HISTORY" title="Imported CSV files"><div className="table-wrap"><table><thead><tr><th>File</th><th>Rows</th><th>Invalid</th><th>Stored</th><th>Digest</th></tr></thead><tbody>{catalogues.map(c => <tr key={c.id}><td><strong>{c.filename}</strong></td><td>{c.rows}</td><td>{c.invalid}</td><td>{c.storage}</td><td className="mono">{c.sha256}…</td></tr>)}</tbody></table></div></Panel>
  </>
}

function Review({ refresh, flash, aiEnabled }) {
  const [status, setStatus] = useState('pending')
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(null)
  const [advice, setAdvice] = useState({})
  useEffect(() => { request(`/proposals?status=${status}`).then(setItems).catch(error => flash(error.message, true)) }, [status])
  async function decide(item, decision) {
    setBusy(item.id)
    try {
      await post(`/proposals/${item.id}/decision`, { decision })
      setItems(current => current.filter(p => p.id !== item.id))
      flash(decision === 'accepted' ? 'Records merged into one canonical part.' : 'Suggestion rejected. Source records remain separate.')
      await refresh()
    } catch (error) { flash(error.message, true) }
    finally { setBusy(null) }
  }
  async function askAI(item) {
    setBusy(item.id)
    try {
      const result = await post(`/proposals/${item.id}/ai-review`, {})
      setAdvice(current => ({ ...current, [item.id]: result }))
    }
    catch (error) { flash(error.message, true) }
    finally { setBusy(null) }
  }
  return <>
    <div className="page-title"><span className="eyebrow">02 / ENTITY RESOLUTION</span><h1>Match review</h1><p>Scores rank suggestions. A review decision is required before any source records are grouped.</p></div>
    <div className="notice"><span>ⓘ</span><p><strong>Fitment is not inferred by a duplicate score.</strong> A merged part only displays the vehicle declarations from its original supplier rows.</p></div>
    <Panel kicker="QUEUE" title="Candidate pairs" action={<div className="tabs">{['pending', 'accepted', 'rejected'].map(value => <button className={status === value ? 'active' : ''} onClick={() => setStatus(value)} key={value}>{value}</button>)}</div>}>
      <div className="proposal-list">{items.map(item => <article className="proposal" key={item.id}>
        <div className="proposal-top"><div><span className="eyebrow">PAIR #{item.id}</span><h3>{item.left.brand} · {item.left.category.replaceAll('_', ' ')}</h3></div><div className="confidence"><strong>{score(item.score)}</strong><span>match score</span></div></div>
        <div className="pair"><Source part={item.left} /><div className="pair-connector">↔</div><Source part={item.right} /></div>
        <div className="signals"><span className={item.signals.exact_part_number ? 'signal-good' : ''}>{item.signals.exact_part_number ? '✓' : '○'} Part number</span><span>{Math.round(item.signals.description_similarity * 100)}% description similarity</span><span className={item.signals.declared_fitment_overlaps ? 'signal-good' : ''}>{item.signals.declared_fitment_overlaps ? '✓' : '○'} Fitment overlap</span></div>
        {advice[item.id] && <div className="ai-advice"><strong>AI suggestion: {advice[item.id].decision.replaceAll('_', ' ')}</strong><p>{advice[item.id].reason}</p><small>Advisory only. You make the decision.</small></div>}
        {status === 'pending' && <div className="proposal-actions"><span>Review the underlying records before merging.</span><div>{aiEnabled && <button className="button button-quiet" disabled={busy === item.id} onClick={() => askAI(item)}>Ask AI</button>}<button className="button button-quiet" disabled={busy === item.id} onClick={() => decide(item, 'rejected')}>Reject</button><button className="button button-primary" disabled={busy === item.id} onClick={() => decide(item, 'accepted')}>Confirm merge</button></div></div>}
      </article>)}{!items.length && <Empty title={`No ${status} pairs`} detail={status === 'pending' ? 'Import another catalogue to find more candidate duplicates.' : 'Decisions will appear here after review.'} />}</div>
    </Panel>
  </>
}

function Fitment({ flash }) {
  const [form, setForm] = useState({ make: 'Aster', model: 'A1', year: '2020', engine: '1.6L' })
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  async function search(event) {
    event.preventDefault(); setBusy(true)
    try { setResults(await request(`/fitment?${new URLSearchParams(form)}`)) }
    catch (error) { flash(error.message, true) }
    finally { setBusy(false) }
  }
  return <>
    <div className="page-title"><span className="eyebrow">03 / COMPATIBILITY</span><h1>Fitment lookup</h1><p>Find parts with an explicit supplier declaration for the vehicle and year you enter.</p></div>
    <div className="notice"><span>ⓘ</span><p>This demo uses fictional brands and vehicles. An engine left blank in a catalogue is <strong>unverified</strong>, not a claim of universal compatibility.</p></div>
    <Panel kicker="SEARCH" title="Vehicle details"><form className="fitment-form" onSubmit={search}>{[
      ['make', 'Make', 'Aster'], ['model', 'Model', 'A1'], ['year', 'Year', '2020'], ['engine', 'Engine', '1.6L (optional)'],
    ].map(([name, label, placeholder]) => <label key={name}><span>{label}</span><input value={form[name]} placeholder={placeholder} required={name !== 'engine'} type={name === 'year' ? 'number' : 'text'} min={name === 'year' ? 1900 : undefined} max={name === 'year' ? 2100 : undefined} onChange={event => setForm(current => ({ ...current, [name]: event.target.value }))} /></label>)}<button className="button button-primary" disabled={busy}>{busy ? 'Searching…' : 'Find declared parts →'}</button></form></Panel>
    {results && <Panel kicker="RESULTS" title={`${results.length} canonical group${results.length === 1 ? '' : 's'} found`}>
      {results.length ? <div className="fit-results">{results.map(group => <div className="fit-result" key={group.canonical_id}><div className="fit-result-head"><div><span className="eyebrow">GROUP #{group.canonical_id}</span><h3>{group.sources[0].brand} {group.sources[0].part_number}</h3></div><span className={`status ${group.status === 'declared' ? 'status-good' : ''}`}>{group.status === 'declared' ? 'Engine declared' : 'Engine unverified'}</span></div><p>{group.sources[0].description}</p><div className="source-chips">{group.sources.map(row => <span key={row.id}>{row.supplier} · {row.sku} · {row.year_start}–{row.year_end}</span>)}</div></div>)}</div> : <Empty title="No supplier declaration found" detail="Check the make, model, year and engine. Absence of a record is not proof that a part is incompatible." />}
    </Panel>}
  </>
}

function Evaluations({ evaluations, refresh, flash, datasets, models, monitoring }) {
  const [threshold, setThreshold] = useState(0.8)
  const [modelVersion, setModelVersion] = useState('rules-tfidf-v1')
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (evaluations.length) request(`/evaluations/${evaluations[0].id}`).then(setDetail).catch(error => flash(error.message, true)) }, [evaluations[0]?.id])
  async function run() {
    setBusy(true)
    try { setDetail(await post('/evaluations', { threshold: Number(threshold), model_version: modelVersion })); await refresh(); flash('Evaluation completed and saved.') }
    catch (error) { flash(error.message, true) }
    finally { setBusy(false) }
  }
  async function selectRun(id) {
    try { setDetail(await request(`/evaluations/${id}`)) }
    catch (error) { flash(error.message, true) }
  }
  return <>
    <div className="page-title"><span className="eyebrow">04 / EXPERIMENTS</span><h1>Evaluations</h1><p>Compare versioned rules and thresholds on curated labeled pairs. Inspect mistakes before trusting a matching rule.</p></div>
    <div className="notice"><span>ⓘ</span><p>Metrics use <strong>{datasets?.current.label_count || 0} synthetic, selected pairs</strong>. Compare runs with the same dataset version. Scoring failures and API server failures are separate measures; neither estimates production accuracy.</p></div>
    <Panel kicker="DATASET LINEAGE" title={`Current dataset ${datasets?.current.version || '—'}`}>
      <p className="muted">{datasets?.current.catalogue_count || 0} catalogues · {datasets?.current.record_count || 0} source rows · {datasets?.current.label_count || 0} labeled pairs. Importing a CSV creates a new fingerprint; saved runs keep their original version.</p>
      <p className="fine-print">{datasets?.versions.length || 0} evaluated dataset version(s) in history.</p>
    </Panel>
    <Panel kicker="NEW RUN" title="Choose a model and threshold"><div className="experiment-controls">
      <label className="model-picker" htmlFor="model-version"><span>Matching model</span><select id="model-version" value={modelVersion} onChange={event => setModelVersion(event.target.value)}>{models?.versions.map(model => <option value={model.id} key={model.id}>{model.id}</option>)}</select><small>{models?.versions.find(model => model.id === modelVersion)?.description}</small></label>
      <div className="threshold-row"><div><label htmlFor="threshold">Minimum match score <strong>{Number(threshold).toFixed(2)}</strong></label><input id="threshold" aria-label="Minimum match score" type="range" min="0.55" max="1" step="0.01" value={threshold} onChange={event => setThreshold(event.target.value)} /><div className="range-labels"><span>More candidates</span><span>Stricter matches</span></div></div><button className="button button-primary" disabled={busy} onClick={run}>{busy ? 'Running…' : 'Run evaluation →'}</button></div>
    </div><p className="fine-print">The review queue continues to use rules-tfidf-v1. Evaluation never merges records.</p></Panel>
    {detail && <><div className="metric-grid">
      <Metric label="Precision" value={percent(detail.precision)} note="Correct / predicted matches" />
      <Metric label="Recall" value={percent(detail.recall)} note="Found / labeled matches" />
      <Metric label="F1 score" value={percent(detail.f1)} note="Precision–recall balance" accent />
      <Metric label="Retrieval @ 3" value={percent(detail.recall_at_3)} note="Positive query in top three" />
    </div>{detail.data_version !== datasets?.current.version && <div className="notice"><span>ⓘ</span><p>This run used dataset {detail.data_version}. The current import set is {datasets?.current.version}; retrieval scores may differ.</p></div>}<div className="two-col">
      <Panel kicker="RUN DETAIL" title={`Experiment #${detail.id}`}><div className="detail-grid">{[
        ['Dataset version', detail.data_version], ['Model version', detail.model_version],
        ['Labeled pairs', detail.label_count], ['Threshold', detail.threshold.toFixed(2)],
        ['Precision @ 1', percent(detail.precision_at_1)], ['Avg scoring', `${detail.avg_latency_ms.toFixed(2)} ms / pair`],
        ['Scoring failures', percent(detail.failure_rate)], ['Mistakes', detail.false_positives + detail.false_negatives],
      ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div></Panel>
      <Panel kicker="ERROR ANALYSIS" title="Where the rule misses"><div className="error-list">{detail.errors?.length ? detail.errors.map((item, i) => <div className="error-row" key={i}><span className={`tag ${item.expected ? 'tag-amber' : 'tag-red'}`}>{item.expected ? 'Missed match' : 'False match'}</span><strong>{item.left.sku} ↔ {item.right.sku}</strong><span>score {score(item.score)}</span></div>) : <Empty title="No mistakes on this sample" detail="The curated set is small; a clean run does not prove general accuracy." />}</div></Panel>
    </div></>}
    <Panel kicker="HISTORY" title="Compare experiment runs"><div className="table-wrap"><table><thead><tr><th>Run</th><th>Model</th><th>Dataset</th><th>Threshold</th><th>Precision</th><th>Recall</th><th>F1</th><th>Retrieval @ 3</th><th>FP / FN</th><th>ms / pair</th></tr></thead><tbody>{evaluations.map(item => <tr className={detail?.id === item.id ? 'row-selected' : ''} onClick={() => selectRun(item.id)} key={item.id}><td><strong>#{item.id}</strong></td><td className="mono">{item.model_version}</td><td className="mono">{item.data_version}</td><td>{item.threshold.toFixed(2)}</td><td>{percent(item.precision)}</td><td>{percent(item.recall)}</td><td><strong>{percent(item.f1)}</strong></td><td>{percent(item.recall_at_3)}</td><td>{item.false_positives} / {item.false_negatives}</td><td>{item.avg_latency_ms.toFixed(2)}</td></tr>)}</tbody></table></div></Panel>
    <Panel kicker="API MONITORING" title={`Recent ${monitoring?.requests || 0} requests`}>
      <div className="monitor-grid"><Metric label="Average latency" value={`${monitoring?.avg_latency_ms || 0} ms`} note="API requests" /><Metric label="P95 latency" value={`${monitoring?.p95_latency_ms || 0} ms`} note="Slowest 5% boundary" /><Metric label="Server failures" value={percent(monitoring?.server_failure_rate)} note="HTTP 5xx only" /><Metric label="Client errors" value={percent(monitoring?.client_error_rate)} note="HTTP 4xx validation and missing resources" /></div>
      <p className="fine-print">Last {monitoring?.window_size || 100} requests, excluding health and monitoring endpoints. Paths omit query strings. Refresh the page for a new snapshot.</p>
    </Panel>
  </>
}

export default function App() {
  const [page, setPage] = useState('overview')
  const [data, setData] = useState({ overview: null, catalogues: [], evaluations: [], datasets: null, models: null, monitoring: null })
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  async function refresh() {
    try {
      const [overview, catalogues, evaluations, datasets, models, monitoring] = await Promise.all([
        request('/overview'), request('/catalogues'), request('/evaluations'),
        request('/datasets'), request('/models'), request('/monitoring'),
      ])
      setData({ overview, catalogues, evaluations, datasets, models, monitoring }); setError(null)
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { refresh() }, [])
  function flash(text, isError = false) {
    setMessage({ text, isError }); window.setTimeout(() => setMessage(null), 6000)
  }
  return <div className="shell">
    <aside className="sidebar"><div className="identity"><div className="logo">P<span>·</span></div><div><strong>PARTS<span>INTEL</span></strong><small>CATALOGUE WORKSPACE</small></div></div>
      <div className="nav-label">WORKSPACE</div><nav aria-label="Main navigation">{NAV.map(([key, label, icon]) => <button key={key} className={page === key ? 'nav-active' : ''} onClick={() => setPage(key)}><span className="nav-icon">{icon}</span>{label}{key === 'review' && data.overview?.pending > 0 && <small>{data.overview.pending}</small>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="sidebar-separator" /><div className="connection"><span className="live-dot" /><div><strong>System online</strong><small>{data.overview?.vector_index || 'Connecting…'}</small></div></div><p>Demo data is fictional. Every compatibility result needs source evidence.</p></div>
    </aside>
    <main className="main"><header className="topbar"><div><span className="breadcrumb">WORKSPACE</span><span className="crumb-divider">/</span><strong>{NAV.find(item => item[0] === page)?.[1]}</strong></div><div className="topbar-right"><span className="topbar-version">{data.overview?.model_version || 'rules-tfidf-v1'}</span><span className="avatar">PI</span></div></header>
      <div className="content">{error && <div className="notice notice-error">Could not reach the API: {error}. Start the backend and refresh this page.</div>}
        {!data.overview ? <div className="loading">Loading catalogue workspace…</div> : <>
          {page === 'overview' && <Overview {...data} go={setPage} />}
          {page === 'catalogues' && <Catalogues catalogues={data.catalogues} refresh={refresh} flash={flash} />}
          {page === 'review' && <Review refresh={refresh} flash={flash} aiEnabled={data.overview.ai_enabled} />}
          {page === 'fitment' && <Fitment flash={flash} />}
          {page === 'evaluations' && <Evaluations evaluations={data.evaluations} datasets={data.datasets} models={data.models} monitoring={data.monitoring} refresh={refresh} flash={flash} />}
        </>}</div>
      <footer>Parts Intelligence · source-backed catalogue demo <span>Built for inspection, not production fitment decisions</span></footer>
    </main>
    {message && <div role="status" className={`toast ${message.isError ? 'toast-error' : ''}`}>{message.text}<button aria-label="Dismiss" onClick={() => setMessage(null)}>×</button></div>}
  </div>
}
