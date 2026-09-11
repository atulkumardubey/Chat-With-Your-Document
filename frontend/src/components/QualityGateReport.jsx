import { useEffect, useState } from 'react'

const METRIC_LABELS = {
  faithfulness: 'Faithfulness',
  answer_relevance: 'Answer Relevance',
  context_precision: 'Context Precision',
  context_recall: 'Context Recall',
  correct_refusal_rate: 'Correct Refusal Rate',
}

// Short labels used inside score chips — must be unique
const CHIP_LABELS = {
  faithfulness:      'Faithful',
  answer_relevance:  'Answer',
  context_precision: 'Precision',
  context_recall:    'Recall',
}

const FAILURE_TYPE_LABELS = {
  retrieval_miss: 'Retrieval Miss',
  chunking_problem: 'Chunking Problem',
  generation_error: 'Generation Error',
  incorrect_answer_to_unanswerable: 'Incorrect Refusal',
  unknown: 'Unknown',
}

// ── Metrics Scorecard ─────────────────────────────────────────────────────────

function ScoreBar({ score, threshold }) {
  const pct = Math.round(score * 100)
  const threshPct = Math.round(threshold * 100)
  const passed = score >= threshold
  return (
    <div className="qg-bar-wrap">
      <div
        className={`qg-bar-fill ${passed ? 'pass' : 'fail'}`}
        style={{ width: `${pct}%` }}
      />
      <div className="qg-bar-threshold" style={{ left: `${threshPct}%` }} title={`Threshold: ${threshPct}%`} />
    </div>
  )
}

function MetricsTable({ metrics, thresholds }) {
  return (
    <div className="qg-metrics-table">
      <div className="qg-metrics-header">
        <span>Metric</span>
        <span style={{ textAlign: 'right' }}>Score</span>
        <span>Progress</span>
        <span style={{ textAlign: 'right' }}>Threshold</span>
        <span style={{ textAlign: 'center' }}>Status</span>
      </div>
      {Object.entries(METRIC_LABELS).map(([key, label]) => {
        if (!(key in metrics)) return null
        const score = metrics[key]
        const threshold = thresholds[key]
        const passed = score >= threshold
        return (
          <div key={key} className="qg-metrics-row">
            <span className="qg-metric-name">{label}</span>
            <span className="qg-metric-score">{(score * 100).toFixed(1)}%</span>
            <div className="qg-metric-bar-col">
              <ScoreBar score={score} threshold={threshold} />
            </div>
            <span className="qg-metric-threshold">≥ {(threshold * 100).toFixed(0)}%</span>
            <span className={`qg-status-badge ${passed ? 'pass' : 'fail'}`}>
              {passed ? 'PASS' : 'FAIL'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Summary Stats ─────────────────────────────────────────────────────────────

function SummaryStats({ summary }) {
  return (
    <div className="qg-summary-stats">
      {[
        { label: 'Total',      value: summary.total,       color: 'var(--text)',         bar: 'var(--border-mid)' },
        { label: 'Answerable', value: summary.answerable,  color: 'var(--accent)',        bar: 'var(--accent)' },
        { label: 'Refusal',    value: summary.unanswerable,color: 'var(--accent-light)',  bar: 'var(--accent-light)' },
        { label: 'Passed',     value: summary.passed,      color: 'var(--green)',         bar: 'var(--green)' },
        { label: 'Failed',     value: summary.failed,      color: 'var(--red)',           bar: 'var(--red)' },
      ].map(({ label, value, color, bar }) => (
        <div key={label} className="qg-stat-card" style={{ borderBottom: `3px solid ${bar}` }}>
          <span className="qg-stat-value" style={{ color }}>{value}</span>
          <span className="qg-stat-label">{label}</span>
        </div>
      ))}
    </div>
  )
}

// ── Top 5 Failures ────────────────────────────────────────────────────────────

function Top5Failures({ results }) {
  const failures = results
    .filter((r) => !r.all_passed)
    .sort((a, b) => {
      // Sort by worst combined score (lowest first)
      const scoreA = (a.faithfulness ?? 1) + (a.answer_relevance ?? 1)
      const scoreB = (b.faithfulness ?? 1) + (b.answer_relevance ?? 1)
      return scoreA - scoreB
    })
    .slice(0, 5)

  if (failures.length === 0) {
    return (
      <div className="qg-no-failures">
        All questions passed — no failures to display.
      </div>
    )
  }

  return (
    <div className="qg-top5-list">
      {failures.map((f, i) => (
        <div key={f.question_id} className="qg-top5-card">
          <div className="qg-top5-rank">#{i + 1}</div>
          <div className="qg-top5-body">
            <div className="qg-top5-header">
              <span className="qg-top5-qid">Q{String(f.question_id).padStart(2, '0')}</span>
              <span className="qg-top5-source">{(f.source_type || (f.answerable ? 'answerable' : 'refusal')).replace(/_/g, ' ')}</span>
              <span className="qg-top5-failure-type">
                {FAILURE_TYPE_LABELS[f.failure_type] ?? f.failure_type ?? 'Unknown'}
              </span>
            </div>
            <div className="qg-top5-question">{f.question}</div>
            {f.answerable && (
              <div className="qg-top5-scores">
                {['faithfulness', 'answer_relevance', 'context_precision', 'context_recall'].map((k) => {
                  const val = f[k]
                  const chipClass = val === undefined ? 'na' : val >= 0.6 ? 'ok' : 'bad'
                  return (
                    <span key={k} className={`qg-top5-score-chip ${chipClass}`}>
                      {CHIP_LABELS[k]}: {val !== undefined ? (val * 100).toFixed(0) + '%' : '—'}
                    </span>
                  )
                })}
              </div>
            )}
            {!f.answerable && (
              <div className="qg-top5-scores">
                <span className={`qg-top5-score-chip ${f.is_correct_refusal ? 'ok' : 'bad'}`}>
                  {f.is_correct_refusal ? 'Correctly Refused' : 'Failed to Refuse'}
                </span>
              </div>
            )}
            {f.answer && (
              <div className="qg-top5-answer">
                <span className="qg-top5-answer-label">Answer: </span>
                {f.answer.slice(0, 160)}{f.answer.length > 160 ? '…' : ''}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Per-question Results ──────────────────────────────────────────────────────

function ResultRow({ r }) {
  const [open, setOpen] = useState(false)
  const passed = r.all_passed
  const isAnswerable = r.answerable

  return (
    <div className={`qg-result-row ${passed ? 'passed' : 'failed'}`}>
      <button className="qg-result-toggle" onClick={() => setOpen((o) => !o)}>
        <span className={`qg-result-dot ${passed ? 'pass' : 'fail'}`} />
        <span className="qg-result-qid">Q{String(r.question_id).padStart(2, '0')}</span>
        <span className="qg-result-type">{(r.source_type || (isAnswerable ? 'answerable' : 'refusal')).replace(/_/g, ' ')}</span>
        <span className="qg-result-question">{r.question}</span>
        {!isAnswerable && (
          <span className={`qg-result-refusal-badge ${r.is_correct_refusal ? 'pass' : 'fail'}`}>
            {r.is_correct_refusal ? 'Refused ✓' : 'Not Refused ✗'}
          </span>
        )}
        {isAnswerable && r.failure_type && (
          <span className="qg-result-failure-tag">
            {FAILURE_TYPE_LABELS[r.failure_type] ?? r.failure_type}
          </span>
        )}
        <span className="qg-result-arrow">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="qg-result-detail">
          {isAnswerable && (
            <div className="qg-result-scores">
              {['faithfulness', 'answer_relevance', 'context_precision', 'context_recall'].map((k) => {
                const val = r[k]
                const cls = val === undefined ? 'na' : val >= 0.6 ? 'ok' : 'bad'
                return (
                  <div key={k} className="qg-mini-score">
                    <span className="qg-mini-label">{METRIC_LABELS[k]}</span>
                    <span className={`qg-mini-value ${cls}`}>
                      {val !== undefined ? (val * 100).toFixed(0) + '%' : '—'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
          {r.answer && (
            <div className="qg-result-answer">
              <span className="qg-detail-label">Answer</span>
              <p>{r.answer}</p>
            </div>
          )}
          {r.contexts && r.contexts.length > 0 && (
            <div className="qg-result-contexts">
              <span className="qg-detail-label">Top Context</span>
              <p className="qg-context-text">{r.contexts[0].slice(0, 300)}…</p>
            </div>
          )}
          {r.error && (
            <div className="qg-result-error">Error: {r.error}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function QualityGateReport({ onClose }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    fetch('/api/quality-gate-report')
      .then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(e.detail || 'Not found'))
        return r.json()
      })
      .then(setReport)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const filteredResults = report?.results?.filter((r) => {
    if (filter === 'passed') return r.all_passed
    if (filter === 'failed') return !r.all_passed
    return true
  }) ?? []

  const isShip = report?.verdict === 'SHIP'

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="qg-panel">
        {/* ── Header ── */}
        <div className="qg-header">
          <div className="qg-header-left">
            <span className="qg-header-icon">🔬</span>
            <div>
              <div className="qg-header-title">RAG Quality Gate</div>
              {report?.document && (
                <div className="qg-header-sub">
                  {report.document.name} · {report.document.pages ?? '?'} pages
                </div>
              )}
            </div>
          </div>
          <div className="qg-header-right">
            {report && (
              <div className={`qg-verdict-badge ${isShip ? 'ship' : 'fix'}`}>
                {isShip ? '✓ SHIP' : '✗ FIX'}
              </div>
            )}
            <button className="close-btn" onClick={onClose}>×</button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="qg-body">
          {loading && (
            <div className="qg-loading">
              <div className="qg-spinner" />
              <span>Loading report…</span>
            </div>
          )}

          {error && (
            <div className="qg-error">
              <div className="qg-error-icon">⚠️</div>
              <div className="qg-error-title">No report found</div>
              <div className="qg-error-hint">{error}</div>
              <code className="qg-error-cmd">
                python -m eval.run_quality_gate --doc-id &lt;id&gt; --questions eval/my_questions.json
              </code>
            </div>
          )}

          {report && (
            <>
              {/* 1. Summary stats */}
              <SummaryStats summary={report.summary} />

              {/* 2. Metrics Scorecard */}
              <div className="qg-section-title">Metrics Scorecard</div>
              <MetricsTable metrics={report.metrics} thresholds={report.thresholds} />

              {/* 3. Top 5 Failures */}
              <div className="qg-section-title" style={{ marginTop: 8 }}>
                Top 5 Failures
              </div>
              <Top5Failures results={report.results} />

              {/* 4. All question results */}
              <div className="qg-section-title" style={{ marginTop: 8 }}>
                All Question Results
                <div className="qg-filter-tabs">
                  {['all', 'passed', 'failed'].map((f) => (
                    <button
                      key={f}
                      className={`qg-filter-tab ${filter === f ? 'active' : ''}`}
                      onClick={() => setFilter(f)}
                    >
                      {f.charAt(0).toUpperCase() + f.slice(1)}
                      {f === 'passed' && ` (${report.summary.passed})`}
                      {f === 'failed' && ` (${report.summary.failed})`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="qg-results-list">
                {filteredResults.map((r) => (
                  <ResultRow key={r.question_id} r={r} />
                ))}
              </div>

              {report.questions_file && (
                <div className="qg-config-line">
                  Questions file: {report.questions_file}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
