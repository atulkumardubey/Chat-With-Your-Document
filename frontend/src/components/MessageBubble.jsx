import { useState } from 'react'

function renderContent(text) {
  // Bold: **text**
  const parts = text.split(/(\*\*[^*]+\*\*)/)
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part
  )
}

function CitationCard({ citation }) {
  const isExcel = citation.source.endsWith('.xlsx') || citation.source.endsWith('.xls')
  const loc = isExcel
    ? `${citation.sheet} · ${citation.row}`
    : `Page ${citation.page}`

  return (
    <div className="citation-card" title="Click to view source">
      <div className="citation-source">
        <span>{isExcel ? '📗' : '📕'}</span>
        <span>{citation.source}</span>
        <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: 4 }}>
          {loc}
        </span>
      </div>
      <div className="citation-snippet">"{citation.snippet}"</div>
    </div>
  )
}

function DocReadyCard({ message }) {
  const isExcel = message.docType === 'excel'
  const meta = isExcel
    ? `${message.sheets ?? '?'} sheet${message.sheets !== 1 ? 's' : ''}`
    : `${message.pages ?? '?'} page${message.pages !== 1 ? 's' : ''}`

  return (
    <div className="doc-ready-card">
      <div className="doc-ready-icon">{isExcel ? '📗' : '📕'}</div>
      <div className="doc-ready-content">
        <div className="doc-ready-header">
          <span className="doc-ready-badge">Indexed</span>
          <span className="doc-ready-meta">{meta}</span>
        </div>
        <div className="doc-ready-name">{message.docName}</div>
        <p className="doc-ready-hint">
          Document indexed and ready. Ask me anything about its contents!
        </p>
      </div>
    </div>
  )
}

export default function MessageBubble({ message }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)

  if (message.role === 'system') {
    return <DocReadyCard message={message} />
  }

  const isUser = message.role === 'user'

  return (
    <div className={`msg-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'assistant'}`}>
        {isUser ? 'You' : '🤖'}
      </div>
      <div className="msg-body">
        <div className={`msg-bubble ${isUser ? 'user' : 'assistant'}`}>
          {renderContent(message.content)}
        </div>
        {!isUser && message.citations?.length > 0 && (
          <div className="citations">
            <button
              type="button"
              className="citation-toggle"
              onClick={() => setSourcesOpen((open) => !open)}
              aria-expanded={sourcesOpen}
            >
              <span className={`citation-toggle-arrow ${sourcesOpen ? 'open' : ''}`}>▸</span>
              Sources ({message.citations.length})
            </button>
            {sourcesOpen && message.citations.map((c, i) => (
              <CitationCard key={i} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
