import { useEffect, useRef, useState } from 'react'

const METRIC_LABELS = {
  faithfulness: 'Faithfulness',
  answer_relevance: 'Answer Relevance',
  context_precision: 'Context Precision',
  context_recall: 'Context Recall',
  correct_refusal_rate: 'Refusal Rate',
}

function MiniScorecard({ metrics, thresholds }) {
  return (
    <div className="eval-scorecard">
      {Object.entries(METRIC_LABELS).map(([key, label]) => {
        if (!(key in metrics)) return null
        const score = metrics[key]
        const threshold = thresholds[key]
        const passed = score >= threshold
        return (
          <div key={key} className="eval-score-row">
            <span className="eval-score-label">{label}</span>
            <div className="eval-score-bar-wrap">
              <div
                className={`eval-score-bar-fill ${passed ? 'pass' : 'fail'}`}
                style={{ width: `${Math.round(score * 100)}%` }}
              />
              <div
                className="eval-score-bar-threshold"
                style={{ left: `${Math.round(threshold * 100)}%` }}
              />
            </div>
            <span className={`eval-score-pct ${passed ? 'pass' : 'fail'}`}>
              {(score * 100).toFixed(0)}%
            </span>
            <span className={`eval-status-chip ${passed ? 'pass' : 'fail'}`}>
              {passed ? 'PASS' : 'FAIL'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function EvalRunModal({ doc, onClose, onViewReport }) {
  const [phase, setPhase] = useState('connecting') // connecting | running | done | error
  const [total, setTotal] = useState(0)
  const [completed, setCompleted] = useState(0)
  const [results, setResults] = useState([])
  const [verdict, setVerdict] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [thresholds, setThresholds] = useState(null)
  const [summary, setSummary] = useState(null)
  const [errorMsg, setErrorMsg] = useState(null)
  const esRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    let es = null

    async function startRun() {
      try {
        const res = await fetch('/api/quality-gate/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ doc_id: doc.id }),
        })
        if (!res.ok) {
          const err = await res.json()
          setErrorMsg(err.detail || 'Failed to start evaluation')
          setPhase('error')
          return
        }
        const { run_id } = await res.json()

        es = new EventSource(`/api/quality-gate/run/${run_id}/events`)
        esRef.current = es

        es.onmessage = (e) => {
          const event = JSON.parse(e.data)

          if (event.type === 'start') {
            setTotal(event.total)
            setPhase('running')
          } else if (event.type === 'progress') {
            setCompleted(event.completed)
            setResults((prev) => [...prev, event.result])
            // Scroll list to bottom
            setTimeout(() => {
              listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
            }, 50)
          } else if (event.type === 'done') {
            setVerdict(event.verdict)
            setMetrics(event.metrics)
            setThresholds(event.thresholds)
            setSummary(event.summary)
            setPhase('done')
            es.close()
          } else if (event.type === 'error') {
            setErrorMsg(event.message)
            setPhase('error')
            es.close()
          }
        }

        es.onerror = () => {
          if (phase !== 'done') {
            setErrorMsg('Connection to server lost.')
            setPhase('error')
          }
          es.close()
        }
      } catch (err) {
        setErrorMsg(err.message)
        setPhase('error')
      }
    }

    startRun()
    return () => { esRef.current?.close() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  const isShip = verdict === 'SHIP'

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && phase === 'done' && onClose()}>
      <div className="eval-panel">
        {/* Header */}
        <div className="eval-header">
          <div className="eval-header-left">
            <span className="eval-header-icon">🔬</span>
            <div>
              <div className="eval-header-title">Running Evaluation</div>
              <div className="eval-header-sub">{doc.name}</div>
            </div>
          </div>
          <div className="eval-header-right">
            {phase === 'done' && (
              <div className={`eval-verdict-badge ${isShip ? 'ship' : 'fix'}`}>
                {isShip ? '✓ SHIP' : '✗ FIX'}
              </div>
            )}
            {(phase === 'done' || phase === 'error') && (
              <button className="close-btn" onClick={onClose}>×</button>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="eval-body">

          {/* Progress bar */}
          {(phase === 'running' || phase === 'connecting') && (
            <div className="eval-progress-section">
              <div className="eval-progress-label">
                {phase === 'connecting' ? (
                  <span>Starting evaluation…</span>
                ) : (
                  <span>{completed} / {total} questions evaluated</span>
                )}
                <span className="eval-progress-pct">{pct}%</span>
              </div>
              <div className="eval-progress-track">
                <div className="eval-progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="eval-progress-hint">
                {phase === 'connecting'
                  ? 'Connecting to server…'
                  : 'Running LLM-as-judge scoring in parallel…'}
              </div>
            </div>
          )}

          {/* Done: scorecard */}
          {phase === 'done' && metrics && thresholds && (
            <>
              <div className="eval-summary-row">
                {[
                  { label: 'Total', value: summary?.total, color: 'var(--text)' },
                  { label: 'Passed', value: summary?.passed, color: 'var(--green)' },
                  { label: 'Failed', value: summary?.failed, color: 'var(--red)' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="eval-summary-chip">
                    <span style={{ color, fontWeight: 800, fontSize: 20 }}>{value}</span>
                    <span className="eval-summary-chip-label">{label}</span>
                  </div>
                ))}
              </div>
              <div className="eval-section-title">Metrics</div>
              <MiniScorecard metrics={metrics} thresholds={thresholds} />
            </>
          )}

          {/* Error */}
          {phase === 'error' && (
            <div className="eval-error">
              <div style={{ fontSize: 32 }}>⚠️</div>
              <div className="eval-error-title">Evaluation Failed</div>
              <div className="eval-error-msg">{errorMsg}</div>
            </div>
          )}

          {/* Per-question live log */}
          {results.length > 0 && (
            <>
              <div className="eval-section-title" style={{ marginTop: 16 }}>
                {phase === 'done' ? 'Question Results' : 'Live Results'}
              </div>
              <div className="eval-results-log" ref={listRef}>
                {results.map((r) => {
                  const passed = r.all_passed
                  const isAnswerable = r.answerable
                  return (
                    <div key={r.question_id} className={`eval-log-row ${passed ? 'pass' : 'fail'}`}>
                      <span className={`eval-log-dot ${passed ? 'pass' : 'fail'}`} />
                      <span className="eval-log-qid">Q{String(r.question_id).padStart(2, '0')}</span>
                      <span className="eval-log-question">{r.question}</span>
                      {!isAnswerable && (
                        <span className={`eval-log-tag ${r.is_correct_refusal ? 'pass' : 'fail'}`}>
                          {r.is_correct_refusal ? 'Refused ✓' : 'Not Refused ✗'}
                        </span>
                      )}
                      {isAnswerable && r.failure_type && (
                        <span className="eval-log-tag fail">{r.failure_type.replace(/_/g, ' ')}</span>
                      )}
                      {isAnswerable && passed && (
                        <span className="eval-log-tag pass">Pass</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {phase === 'done' && (
          <div className="eval-footer">
            <button className="eval-footer-view-btn" onClick={() => { onClose(); onViewReport() }}>
              View Full Report
            </button>
            <button className="eval-footer-close-btn" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
