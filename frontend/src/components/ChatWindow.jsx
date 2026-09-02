import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

const SUGGESTIONS = [
  'What was the total revenue in Q3?',
  'Which product had the highest sales?',
  'What is the operating profit margin?',
  'Summarise the Excel data',
]

export default function ChatWindow({ messages, isTyping, onSend, hasDocs }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  const send = () => {
    const trimmed = input.trim()
    if (!trimmed) return
    onSend(trimmed)
    setInput('')
    textareaRef.current.style.height = 'auto'
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  return (
    <>
      <div className="chat-header">
        <div className="chat-header-title">
          <h1>Chat With Your Document</h1>
          <span className="chat-header-badge">Demo</span>
        </div>
        <div className="chat-header-info">
          <span className="header-dot" />
          {hasDocs ? `${messages.filter(m => m.role === 'user').length} questions asked` : 'No documents uploaded'}
        </div>
      </div>

      <div className="messages-area">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h2>Ask anything about your documents</h2>
            <p>Upload a PDF or Excel file, then type a question. Every answer comes with a citation pointing to the exact source.</p>
            <div className="suggestion-chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => onSend(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isTyping && (
              <div className="typing-row">
                <div className="msg-avatar assistant">🤖</div>
                <div className="typing-bubble">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="input-bar-wrap">
        <div className="input-bar">
          <textarea
            ref={textareaRef}
            placeholder="Ask a question about your documents…"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKey}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={send}
            disabled={!input.trim() || isTyping}
            title="Send (Enter)"
          >
            ↑
          </button>
        </div>
        <div className="input-hint">Press Enter to send · Shift+Enter for new line</div>
      </div>
    </>
  )
}
