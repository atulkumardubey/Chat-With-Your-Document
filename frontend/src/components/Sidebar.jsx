import { useState } from 'react'

export default function Sidebar({ docs, activeDoc, onSelectDoc, onAddDoc, onDeleteDoc, onOpenQualityGate }) {
  const [search, setSearch] = useState('')

  const handleDelete = (e, doc) => {
    e.stopPropagation()
    if (window.confirm(`Delete "${doc.name}"? This removes it and all its indexed data permanently.`)) {
      onDeleteDoc(doc.id)
    }
  }

  const filtered = docs.filter((d) =>
    d.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <div>
            <div className="sidebar-logo-text">DocChat</div>
            <div className="sidebar-logo-sub">Classic RAG · v1</div>
          </div>
          <button className="sidebar-new-btn" onClick={onAddDoc} title="Upload document">+</button>
        </div>

        <div className="sidebar-search">
          <span className="sidebar-search-icon">🔍</span>
          <input
            placeholder="Search documents…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="sidebar-section-label">
        Indexed Documents
        {docs.length > 0 && (
          <span style={{ marginLeft: 6, color: 'var(--accent)', fontWeight: 700 }}>
            ({docs.length})
          </span>
        )}
      </div>

      <div className="sidebar-docs">
        {filtered.length === 0 && search && (
          <div style={{ padding: '12px 8px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
            No documents match "{search}"
          </div>
        )}
        {filtered.map((doc) => (
          <div
            key={doc.id}
            className={`doc-item ${activeDoc?.id === doc.id ? 'active' : ''}`}
            onClick={() => onSelectDoc(doc)}
          >
            <div className={`doc-icon ${doc.type}`}>
              {doc.type === 'pdf' ? '📕' : '📗'}
            </div>
            <div className="doc-info">
              <div className="doc-name">{doc.name}</div>
              <div className="doc-meta">
                {doc.type === 'pdf'
                  ? `${doc.pages ?? '?'} pages`
                  : `${doc.sheets ?? '?'} sheet${doc.sheets !== 1 ? 's' : ''}`}
                {' · '}{doc.uploadedAt ?? ''}
              </div>
            </div>
            <div className={`doc-status ${doc.status}`} title={doc.status} />
            <button
              type="button"
              className="doc-delete-btn"
              title="Delete document"
              onClick={(e) => handleDelete(e, doc)}
            >
              🗑
            </button>
          </div>
        ))}
      </div>

      <button className="sidebar-add-btn" onClick={onAddDoc}>
        <span style={{ fontSize: 18, lineHeight: 1 }}>+</span> Upload Document
      </button>

      <button className="sidebar-quality-gate-btn" onClick={onOpenQualityGate}>
        <span className="sqg-icon">🔬</span>
        <span className="sqg-label">
          <span className="sqg-title">RAG Quality Gate</span>
          <span className="sqg-sub">View eval report</span>
        </span>
        <span className="sqg-arrow">›</span>
      </button>

      <div className="sidebar-footer">
        Answers are grounded only in<br />what you've uploaded here.
      </div>
    </aside>
  )
}
