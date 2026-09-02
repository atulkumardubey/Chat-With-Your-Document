export default function Sidebar({ docs, activeDoc, onSelectDoc, onAddDoc }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">📄</div>
        <div>
          <div className="sidebar-logo-text">DocChat</div>
          <div className="sidebar-logo-sub">Classic RAG · Level 1</div>
        </div>
      </div>

      <div className="sidebar-section-label">Indexed Documents</div>

      <div className="sidebar-docs">
        {docs.map((doc) => (
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
                  ? `${doc.pages} pages`
                  : `${doc.sheets} sheet${doc.sheets !== 1 ? 's' : ''}`}{' '}
                · {doc.uploadedAt}
              </div>
            </div>
            <div className={`doc-status ${doc.status}`} title={doc.status} />
          </div>
        ))}
      </div>

      <button className="sidebar-add-btn" onClick={onAddDoc}>
        <span style={{ fontSize: 16 }}>+</span> Add Document
      </button>

      <div className="sidebar-footer">
        Answers are grounded only in<br />what you've uploaded here.
      </div>
    </aside>
  )
}
