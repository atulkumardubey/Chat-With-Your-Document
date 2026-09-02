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

export default function MessageBubble({ message }) {
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
            <div className="citation-label">Sources</div>
            {message.citations.map((c, i) => (
              <CitationCard key={i} citation={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
