import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import UploadPanel from './components/UploadPanel'
import './App.css'

export default function App() {
  const [docs, setDocs] = useState([])
  const [messagesByDoc, setMessagesByDoc] = useState({})
  const [showUpload, setShowUpload] = useState(false)
  const [activeDoc, setActiveDoc] = useState(null)
  const [isTyping, setIsTyping] = useState(false)
  const [theme, setTheme] = useState('dark')
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

    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData })
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
      const doc = await res.json()
      setDocs((prev) => prev.map((d) => (d.id === placeholder.id ? doc : d)))
      setActiveDoc(doc)
      setMessagesByDoc((prev) => ({
        ...prev,
        [doc.id]: [
          ...(prev[doc.id] ?? []),
          {
            id: Date.now(),
            role: 'system',
            docName: doc.name,
            docType: doc.type,
            pages: doc.pages,
            sheets: doc.sheets,
          },
        ],
      }))
    } catch (err) {
      setDocs((prev) => prev.map((d) => (d.id === placeholder.id ? { ...d, status: 'failed' } : d)))
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
        />
      </main>
      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onUpload={handleUpload} />
      )}
    </div>
  )
}
