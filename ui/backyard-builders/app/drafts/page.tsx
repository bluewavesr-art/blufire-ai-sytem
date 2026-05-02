'use client'

import { useEffect, useState } from 'react'

interface Draft {
  created_at: string
  to: string
  subject: string
  body: string
  list_unsubscribe: string
  status: string
}

export default function DraftsPage() {
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  async function load() {
    setLoading(true)
    const res = await fetch('/api/drafts')
    const data = await res.json()
    setDrafts((data.drafts ?? []).filter((d: Draft) => d.to))
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function updateStatus(rowIndex: number, status: string) {
    setSaving(rowIndex)
    await fetch('/api/drafts', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row: rowIndex + 1, status }),
    })
    setDrafts((prev) =>
      prev.map((d, i) => (i === rowIndex ? { ...d, status } : d))
    )
    setSaving(null)
  }

  if (loading) return <div className="text-gray-400 mt-8">Loading drafts…</div>

  const pending = drafts.filter((d) => !d.status || d.status === 'pending')
  const rest = drafts.filter((d) => d.status && d.status !== 'pending')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Email Drafts</h1>
        <p className="text-sm text-gray-500 mt-1">
          Review AI-written outreach emails. Mark as Sent when you've sent them from Gmail,
          or Skip to dismiss.
        </p>
      </div>

      {pending.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 text-gray-400 text-sm">
          No pending drafts. New ones appear after the 6 AM daily run.
        </div>
      )}

      <div className="space-y-3">
        {pending.map((d, i) => {
          const realIndex = drafts.indexOf(d)
          const isOpen = expanded === realIndex
          return (
            <div key={realIndex} className="bg-white rounded-xl border border-gray-100 shadow-sm">
              <button
                className="w-full text-left px-5 py-4 flex items-center gap-3"
                onClick={() => setExpanded(isOpen ? null : realIndex)}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900 truncate">{d.subject}</div>
                  <div className="text-sm text-gray-500 truncate">To: {d.to}</div>
                </div>
                <span className="text-xs text-gray-300">{d.created_at?.slice(0, 10)}</span>
                <span className="text-gray-400 text-xs">{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && (
                <div className="border-t border-gray-50 px-5 py-4 space-y-4">
                  <div className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed bg-gray-50 rounded-lg p-4 font-mono">
                    {d.body}
                  </div>
                  <div className="flex gap-3">
                    <button
                      disabled={saving === realIndex}
                      onClick={() => updateStatus(realIndex, 'sent')}
                      className="px-4 py-2 bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                    >
                      {saving === realIndex ? 'Saving…' : '✓ Mark Sent'}
                    </button>
                    <button
                      disabled={saving === realIndex}
                      onClick={() => updateStatus(realIndex, 'skipped')}
                      className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-600 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                    >
                      Skip
                    </button>
                    <a
                      href={`mailto:${d.to}?subject=${encodeURIComponent(d.subject)}&body=${encodeURIComponent(d.body)}`}
                      className="px-4 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-sm font-medium rounded-lg transition-colors"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open in Gmail
                    </a>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {rest.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm text-gray-400 hover:text-gray-600 select-none">
            Show {rest.length} completed draft{rest.length !== 1 ? 's' : ''}
          </summary>
          <div className="mt-3 space-y-2">
            {rest.map((d, i) => {
              const realIndex = drafts.indexOf(d)
              return (
                <div key={realIndex} className="bg-white rounded-xl border border-gray-100 shadow-sm px-5 py-3 flex items-center gap-3 opacity-60">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{d.subject}</div>
                    <div className="text-xs text-gray-400 truncate">To: {d.to}</div>
                  </div>
                  <StatusBadge status={d.status} />
                </div>
              )
            })}
          </div>
        </details>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    sent: 'bg-green-100 text-green-700',
    skipped: 'bg-gray-100 text-gray-500',
    pending: 'bg-yellow-100 text-yellow-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}
