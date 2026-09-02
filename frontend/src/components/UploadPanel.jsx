import { useState, useRef } from 'react'

export default function UploadPanel({ onClose, onUpload }) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  const handleFile = (e) => {
    const file = e.target.files[0]
    if (file) onUpload(file)
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="upload-panel">
        <div className="upload-panel-header">
          <h2>Upload a Document</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="upload-body">
          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current.click()}
          >
            <div className="drop-zone-icon">📁</div>
            <h3>Drop your file here</h3>
            <p>or click to browse</p>
            <div className="drop-zone-formats">
              <span className="format-tag">PDF</span>
              <span className="format-tag">XLSX</span>
              <span className="format-tag">XLS</span>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.xlsx,.xls"
              style={{ display: 'none' }}
              onChange={handleFile}
            />
          </div>
          <div className="upload-info">
            <strong>What happens after upload?</strong><br />
            Your document is chunked, embedded, and stored in a vector database. Each chunk preserves its source location so every answer can cite the exact page or row it came from.
          </div>
        </div>
      </div>
    </div>
  )
}
