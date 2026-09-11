import { useState } from 'react'

const METRICS = [
  { key: 'faithfulness', label: 'Faithfulness', score: 85, desc: 'Answer grounded in source documents' },
  { key: 'relevance',    label: 'Relevance',    score: 82, desc: 'Answer addresses the question asked' },
  { key: 'precision',   label: 'Precision',    score: 74, desc: 'Retrieved chunks are on-topic' },
  { key: 'recall',      label: 'Recall',       score: 71, desc: 'All key facts from source captured' },
]

const QUESTIONS = [
  { id: 1, q: 'What is the definition of financial statements?',       score: 90, status: 'pass' },
  { id: 2, q: 'For what three purposes are statements audited?',        score: 85, status: 'pass' },
  { id: 3, q: 'How does the document describe the Balance Sheet?',      score: 88, status: 'pass' },
  { id: 4, q: 'What does the cash flow statement undo?',               score: 64, status: 'warn' },
  { id: 5, q: 'What is Goodwill and how is it classified?',            score: 82, status: 'pass' },
  { id: 6, q: 'What is the formula to calculate Goodwill?',           score: 43, status: 'fail' },
  { id: 7, q: 'What are the three types of intangible assets?',        score: 91, status: 'pass' },
  { id: 8, q: 'What is unearned or deferred revenue?',                score: 76, status: 'warn' },
  { id: 9, q: 'What are contingency recording conditions?',           score: 80, status: 'pass' },
  { id: 10, q: 'Are contingent gains recorded in statements?',         score: 89, status: 'pass' },
]

const OVERALL = Math.round(METRICS.reduce((s, m) => s + m.score, 0) / METRICS.length)

function statusColor(score) {
  if (score >= 80) return 'var(--green)'
  if (score >= 60) return 'var(--yellow)'
  return 'var(--red)'
}

function statusLabel(status) {
  return { pass: 'Pass', warn: 'Review', fail: 'Fail' }[status]
}

function CircleGauge({ value }) {
  const r = 52
  const circ = 2 * Math.PI * r
  const offset = circ - (value / 100) * circ
  const color = statusColor(value)

  return (
    <svg className="qr-gauge-svg" viewBox="0 0 140 140" aria-label={`Overall score ${value}%`}>
      {/* Track */}
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--border)" strokeWidth="10" />
      {/* Fill */}
      <circle
        cx="70" cy="70" r={r} fill="none"
        stroke={color} strokeWidth="10"
        strokeDasharray={`${circ}`}
        strokeDashoffset={`${offset}`}
        strokeLinecap="round"
        transform="rotate(-90 70 70)"
        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(.4,0,.2,1)' }}
      />
      <text x="70" y="63" textAnchor="middle" fill="var(--text)" fontSize="26" fontWeight="700">{value}%</text>
      <text x="70" y="82" textAnchor="middle" fill="var(--text-muted)" fontSize="11">Overall</text>
    </svg>
  )
}

function MetricBar({ label, score, desc }) {
  const color = statusColor(score)
  return (
    <div className="qr-metric-row" role="group" aria-label={`${label}: ${score}%`}>
      <div className="qr-metric-top">
        <span className="qr-metric-label">{label}</span>
        <span className="qr-metric-pct" style={{ color }}>{score}%</span>
      </div>
      <div className="qr-bar-track" title={`${score}%`}>
        <div
          className="qr-bar-fill"
          style={{ width: `${score}%`, background: color }}
        />
      </div>
      <div className="qr-metric-desc">{desc}</div>
    </div>
  )
}

function ScoreBadge({ status, score }) {
  const color = statusColor(score)
  return (
    <span className="qr-badge" style={{ color, borderColor: color, background: `${color}18` }}>
      {statusLabel(status)}
    </span>
  )
}

export default function QualityReport({ onClose }) {
  const [tab, setTab] = useState('overview')

  const passed  = QUESTIONS.filter(q => q.status === 'pass').length
  const warned  = QUESTIONS.filter(q => q.status === 'warn').length
  const failed  = QUESTIONS.filter(q => q.status === 'fail').length

  return (
    <div className="qr-overlay" role="dialog" aria-modal="true" aria-label="RAG Quality Report">
      <div className="qr-panel">

        {/* ── Header ── */}
        <div className="qr-header">
          <div>
            <div className="qr-title">RAG Quality Report</div>
            <div className="qr-subtitle">LLM-as-judge evaluation · {QUESTIONS.length} questions</div>
          </div>
          <button className="qr-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* ── Tabs ── */}
        <div className="qr-tabs">
          {['overview', 'questions'].map(t => (
            <button
              key={t}
              className={`qr-tab ${tab === t ? 'active' : ''}`}
              onClick={() => setTab(t)}
            >
              {t === 'overview' ? 'Overview' : 'Question Results'}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div className="qr-body">

            {/* ── Top row: gauge + stat tiles ── */}
            <div className="qr-top-row">
              <div className="qr-gauge-wrap">
                <CircleGauge value={OVERALL} />
                <div className="qr-gauge-legend">
                  <span className="qr-legend-dot" style={{ background: 'var(--green)' }} />
                  <span>≥ 80 Pass</span>
                  <span className="qr-legend-dot" style={{ background: 'var(--yellow)' }} />
                  <span>60–79 Review</span>
                  <span className="qr-legend-dot" style={{ background: 'var(--red)' }} />
                  <span>&lt; 60 Fail</span>
                </div>
              </div>

              <div className="qr-stat-grid">
                <div className="qr-stat-tile">
                  <div className="qr-stat-num" style={{ color: 'var(--green)' }}>{passed}</div>
                  <div className="qr-stat-lbl">Passed</div>
                </div>
                <div className="qr-stat-tile">
                  <div className="qr-stat-num" style={{ color: 'var(--yellow)' }}>{warned}</div>
                  <div className="qr-stat-lbl">Review</div>
                </div>
                <div className="qr-stat-tile">
                  <div className="qr-stat-num" style={{ color: 'var(--red)' }}>{failed}</div>
                  <div className="qr-stat-lbl">Failed</div>
                </div>
                <div className="qr-stat-tile">
                  <div className="qr-stat-num" style={{ color: 'var(--accent)' }}>{QUESTIONS.length}</div>
                  <div className="qr-stat-lbl">Total Q&A</div>
                </div>
              </div>
            </div>

            {/* ── Metric bars ── */}
            <div className="qr-section-label">Metric Breakdown</div>
            <div className="qr-metrics-list">
              {METRICS.map(m => (
                <MetricBar key={m.key} label={m.label} score={m.score} desc={m.desc} />
              ))}
            </div>
          </div>
        )}

        {tab === 'questions' && (
          <div className="qr-body">
            <div className="qr-section-label">Question-by-Question Results</div>
            <div className="qr-table-wrap">
              <table className="qr-table" aria-label="Question results">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Question</th>
                    <th>Score</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {QUESTIONS.map(q => (
                    <tr key={q.id}>
                      <td className="qr-td-id">{q.id}</td>
                      <td className="qr-td-q">{q.q}</td>
                      <td className="qr-td-score">
                        <div className="qr-inline-bar-wrap">
                          <div
                            className="qr-inline-bar"
                            style={{ width: `${q.score}%`, background: statusColor(q.score) }}
                          />
                          <span style={{ color: statusColor(q.score) }}>{q.score}%</span>
                        </div>
                      </td>
                      <td><ScoreBadge status={q.status} score={q.score} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
