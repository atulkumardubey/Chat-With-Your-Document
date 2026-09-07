import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

const FEATURE_CARDS = [
  { icon: '📊', title: 'Research & Analysis',  sub: 'Ask deep questions across your docs',   prompt: 'What are the key findings in the document?' },
  { icon: '📝', title: 'Summarise Content',     sub: 'Get a concise overview instantly',       prompt: 'Summarise the main points of the document' },
  { icon: '🔢', title: 'Extract Data',          sub: 'Pull numbers, tables, and figures',      prompt: 'What are the key numbers and figures?' },
  { icon: '💡', title: 'Find Insights',         sub: 'Surface trends and recommendations',     prompt: 'What insights or recommendations are mentioned?' },
]

export default function ChatWindow({ messages, isTyping, onSend, hasDocs, activeDoc, theme, onToggleTheme }) {
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
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  return (
    <>
      {/* ── Header ── */}
      <div className="chat-header">
        <div className="chat-header-title">
          <h1>{activeDoc ? activeDoc.name : 'Chat With Your Document'}</h1>
          <span className="chat-header-badge">{activeDoc ? 'Scoped' : 'All Docs'}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="chat-header-info">
            <span className="header-dot" />
            {hasDocs
              ? `${messages.filter((m) => m.role === 'user').length} question${messages.filter(m=>m.role==='user').length!==1?'s':''} asked`
              : 'No documents uploaded'}
          </div>
          <button className="theme-toggle" onClick={onToggleTheme} title="Switch theme">
            {theme === 'dark' ? 'Light' : 'Dark'}
            <div className="theme-toggle-knob">
              {theme === 'dark' ? '☀️' : '🌙'}
            </div>
          </button>
        </div>
      </div>

      {/* ── Messages / Empty state ── */}
      <div className="messages-area">
        {messages.length === 0 ? (
          <div className="empty-state">
            {/* 3-D glowing orb */}
            <div className="orb-wrap">
              <div className="orb" />
              <div className="orb-ring" />
            </div>

            <div className="empty-welcome">Welcome to DocChat</div>
            <h2>What can I do to help?</h2>
            <p>
              Upload a PDF or Excel file, then ask anything in plain English.
              Every answer is grounded in your documents with exact source citations.
            </p>

            {/* Feature cards */}
            <div className="feature-cards">
              {FEATURE_CARDS.map((card) => (
                <button
                  key={card.title}
                  className="feature-card"
                  onClick={() => onSend(card.prompt)}
                >
                  <div className="feature-card-icon">{card.icon}</div>
                  <div className="feature-card-title">{card.title}</div>
                  <div className="feature-card-sub">{card.sub}</div>
                </button>
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
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div className="typing-bubble">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', paddingLeft: 4 }}>
                    Analysing documents…
                  </span>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input bar ── */}
      <div className="input-bar-wrap">
        <div className="input-bar">
          <button className="attach-btn" title="Attach file" onClick={() => {}}>📎</button>
          <textarea
            ref={textareaRef}
            placeholder="Ask anything about your documents…"
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
