import { useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import UploadPanel from './components/UploadPanel'
import './App.css'

const DEMO_DOCS = [
  {
    id: 1,
    name: 'Q3_Financial_Report.pdf',
    type: 'pdf',
    pages: 24,
    status: 'indexed',
    uploadedAt: '2 min ago',
  },
  {
    id: 2,
    name: 'Sales_Data_2024.xlsx',
    type: 'excel',
    sheets: 3,
    status: 'indexed',
    uploadedAt: '2 min ago',
  },
]

const DEMO_MESSAGES = [
  {
    id: 1,
    role: 'user',
    content: 'What was the total revenue in Q3?',
  },
  {
    id: 2,
    role: 'assistant',
    content:
      'The total revenue for Q3 2024 was **$4.82 million**, representing a 12.3% increase compared to Q3 2023 ($4.29 million). This growth was primarily driven by a 18% rise in enterprise subscriptions and a 9% uptick in professional services.',
    citations: [
      { source: 'Q3_Financial_Report.pdf', page: 5, snippet: 'Total Revenue Q3 2024: $4,820,000 — up 12.3% YoY' },
      { source: 'Q3_Financial_Report.pdf', page: 8, snippet: 'Enterprise subscriptions grew 18%, contributing $2.1M to total revenue.' },
    ],
  },
  {
    id: 3,
    role: 'user',
    content: 'Which product category had the highest sales in the Excel data?',
  },
  {
    id: 4,
    role: 'assistant',
    content:
      'Based on the Sales_Data_2024.xlsx file, **Cloud Infrastructure** was the top-performing product category with $1,940,000 in sales — accounting for 40.2% of total revenue. It was followed by Security Suite ($1,100,000) and Data Analytics ($780,000).',
    citations: [
      { source: 'Sales_Data_2024.xlsx', sheet: 'Sheet1', row: 'Row 3', snippet: 'Cloud Infrastructure | Q3 Sales: $1,940,000 | Growth: 22%' },
      { source: 'Sales_Data_2024.xlsx', sheet: 'Summary', row: 'Row 1', snippet: 'Top category by revenue: Cloud Infrastructure (40.2% share)' },
    ],
  },
]

export default function App() {
  const [docs, setDocs] = useState(DEMO_DOCS)
  const [messages, setMessages] = useState(DEMO_MESSAGES)
  const [showUpload, setShowUpload] = useState(false)
  const [activeDoc, setActiveDoc] = useState(null)
  const [isTyping, setIsTyping] = useState(false)

  const handleSend = (text) => {
    const userMsg = { id: Date.now(), role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setIsTyping(true)

    setTimeout(() => {
      const botMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: getDemoResponse(text),
        citations: getDemoCitations(text),
      }
      setMessages((prev) => [...prev, botMsg])
      setIsTyping(false)
    }, 1400)
  }

  const handleUpload = (file) => {
    const isExcel = file.name.endsWith('.xlsx') || file.name.endsWith('.xls')
    const newDoc = {
      id: Date.now(),
      name: file.name,
      type: isExcel ? 'excel' : 'pdf',
      pages: isExcel ? undefined : Math.floor(Math.random() * 30) + 5,
      sheets: isExcel ? Math.floor(Math.random() * 4) + 1 : undefined,
      status: 'indexing',
      uploadedAt: 'just now',
    }
    setDocs((prev) => [...prev, newDoc])
    setShowUpload(false)
    setTimeout(() => {
      setDocs((prev) => prev.map((d) => (d.id === newDoc.id ? { ...d, status: 'indexed' } : d)))
    }, 2000)
  }

  return (
    <div className="app-root">
      <Sidebar
        docs={docs}
        activeDoc={activeDoc}
        onSelectDoc={setActiveDoc}
        onAddDoc={() => setShowUpload(true)}
      />
      <main className="main-area">
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          onSend={handleSend}
          hasDocs={docs.length > 0}
        />
      </main>
      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onUpload={handleUpload} />
      )}
    </div>
  )
}

function getDemoResponse(text) {
  const t = text.toLowerCase()
  if (t.includes('profit') || t.includes('margin'))
    return 'The operating profit margin for Q3 2024 was **21.4%**, up from 18.9% in Q3 2023. Net profit after tax stood at **$847,000**. Cost optimisations in infrastructure contributed roughly 2.1 percentage points to the margin expansion.'
  if (t.includes('employee') || t.includes('headcount'))
    return 'As of Q3 2024, the company headcount was **342 full-time employees**, a 15% increase from 298 at the same time last year. Engineering represented the largest function at 38% of total headcount.'
  if (t.includes('chart') || t.includes('image') || t.includes('graph'))
    return 'The bar chart on page 11 of the PDF illustrates quarterly revenue trends from 2022–2024. Note that chart content was extracted via OCR — text answers are fully cited, but chart image queries may have lower accuracy because the answer lives inside a raster image rather than in text.'
  if (t.includes('excel') || t.includes('sheet') || t.includes('row'))
    return 'The Excel file contains **3 sheets**: Raw Data, Pivot Summary, and Regional Breakdown. The markdown-table serialisation format was used during indexing, which preserved column relationships and produced the most accurate retrieval results in testing.'
  return "I couldn't find a specific answer to that question in the indexed documents. Try rephrasing, or check that the relevant document has been uploaded and indexed (green dot in the sidebar). Every answer I give is grounded only in what was handed to me — I won't fabricate information."
}

function getDemoCitations(text) {
  const t = text.toLowerCase()
  if (t.includes('profit') || t.includes('margin'))
    return [
      { source: 'Q3_Financial_Report.pdf', page: 12, snippet: 'Operating profit margin: 21.4% (Q3 2024) vs 18.9% (Q3 2023)' },
      { source: 'Q3_Financial_Report.pdf', page: 14, snippet: 'Net profit after tax: $847,000' },
    ]
  if (t.includes('employee') || t.includes('headcount'))
    return [
      { source: 'Q3_Financial_Report.pdf', page: 19, snippet: 'FTE count: 342 as of September 2024 (+15% YoY)' },
    ]
  return [
    { source: 'Q3_Financial_Report.pdf', page: 1, snippet: 'Executive summary — Q3 2024 results overview' },
  ]
}
