import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import UploadPanel from './components/UploadPanel'
import QualityGateReport from './components/QualityGateReport'
import EvalRunModal from './components/EvalRunModal'
import './App.css'

export default function App() {
  const [docs, setDocs] = useState([])
  const [messagesByDoc, setMessagesByDoc] = useState({})
  const [showUpload, setShowUpload] = useState(false)
  const [activeDoc, setActiveDoc] = useState(null)
  const [isTyping, setIsTyping] = useState(false)
  const [theme, setTheme] = useState('dark')
  const [showQualityGate, setShowQualityGate] = useState(false)
  const [showEvalRun, setShowEvalRun] = useState(false)
  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  const docKey = activeDoc?.id ?? 'all'
  const messages = messagesByDoc[docKey] ?? []

  useEffect(() => {
    fetch('/api/documents')
      .then((res) => res.json())
      .then(setDocs)
      .catch(() => setDocs([]))
  }, [])

  const handleSend = async (text) => {
    // Captured at send time so the reply lands in the right thread even if the user
    // switches the active document while the request is in flight.
    const key = docKey
    const selectedDocId = activeDoc?.id ?? null
    const appendMessage = (msg) =>
      setMessagesByDoc((prev) => ({ ...prev, [key]: [...(prev[key] ?? []), msg] }))

    appendMessage({ id: Date.now(), role: 'user', content: text })
    setIsTyping(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, selectedDocId }),
      })
      if (!res.ok) throw new Error(`Chat request failed: ${res.status}`)
      const data = await res.json()
      appendMessage({ id: Date.now() + 1, role: 'assistant', content: data.content, citations: data.citations })
    } catch (err) {
      appendMessage({
        id: Date.now() + 1,
        role: 'assistant',
        content: `Something went wrong reaching the backend: ${err.message}`,
        citations: [],
      })
    } finally {
      setIsTyping(false)
    }
  }

  const handleUpload = async (file) => {
    setShowUpload(false)
    const formData = new FormData()
    formData.append('file', file)

    const placeholder = {
      id: `pending-${Date.now()}`,
      name: file.name,
      type: file.name.endsWith('.xlsx') || file.name.endsWith('.xls') ? 'excel' : 'pdf',
      status: 'indexing',
      uploadedAt: 'just now',
    }
    setDocs((prev) => [...prev, placeholder])
    setActiveDoc(placeholder)

    let doc
    try {
      // POST /api/upload returns immediately with status='indexing'.
      // Heavy work (parse → chunk → embed → store) runs in a background task on the server.
      const res = await fetch('/api/upload', { method: 'POST', body: formData })
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
      doc = await res.json()
    } catch (err) {
      setDocs((prev) => prev.map((d) => (d.id === placeholder.id ? { ...d, status: 'failed' } : d)))
      return
    }

    // Replace placeholder immediately so the doc ID is correct.
    setDocs((prev) => prev.map((d) => (d.id === placeholder.id ? doc : d)))
    setActiveDoc(doc)

    // Poll until the server finishes indexing (or fails).
    const MAX_POLLS = 60          // up to 5 minutes (60 × 5 s)
    const POLL_INTERVAL_MS = 5000
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      try {
        const listRes = await fetch('/api/documents')
        if (!listRes.ok) break
        const allDocs = await listRes.json()
        const updated = allDocs.find((d) => d.id === doc.id)
        if (!updated) break
        setDocs((prev) => prev.map((d) => (d.id === doc.id ? updated : d)))
        setActiveDoc((prev) => (prev?.id === doc.id ? updated : prev))
        if (updated.status === 'indexed') {
          // Show the "document ready" system message once indexing completes.
          setMessagesByDoc((prev) => ({
            ...prev,
            [updated.id]: [
              ...(prev[updated.id] ?? []),
              {
                id: Date.now(),
                role: 'system',
                docName: updated.name,
                docType: updated.type,
                pages: updated.pages,
                sheets: updated.sheets,
              },
            ],
          }))
          break
        }
        if (updated.status === 'failed') break
      } catch {
        break
      }
    }
  }

  const handleDeleteDoc = async (docId) => {
    try {
      const res = await fetch(`/api/documents/${docId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
      setDocs((prev) => prev.filter((d) => d.id !== docId))
      setActiveDoc((prev) => (prev?.id === docId ? null : prev))
    } catch (err) {
      alert(`Could not delete document: ${err.message}`)
    }
  }

  return (
    <div className={`app-root ${theme}`}>
      <Sidebar
        docs={docs}
        activeDoc={activeDoc}
        onSelectDoc={setActiveDoc}
        onAddDoc={() => setShowUpload(true)}
        onDeleteDoc={handleDeleteDoc}
        onOpenQualityGate={() => setShowQualityGate(true)}
      />
      <main className="main-area">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSend={handleSend}
          hasDocs={docs.length > 0}
          activeDoc={activeDoc}
          theme={theme}
          onToggleTheme={toggleTheme}
          onRunEval={() => setShowEvalRun(true)}
        />
      </main>
      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onUpload={handleUpload} />
      )}
      {showQualityGate && (
        <QualityGateReport onClose={() => setShowQualityGate(false)} />
      )}
      {showEvalRun && activeDoc && (
        <EvalRunModal
          doc={activeDoc}
          onClose={() => setShowEvalRun(false)}
          onViewReport={() => setShowQualityGate(true)}
        />
      )}
    </div>
  )
}
