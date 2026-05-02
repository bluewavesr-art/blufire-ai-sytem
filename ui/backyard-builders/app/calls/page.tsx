'use client'

import { useEffect, useState } from 'react'

interface CallItem {
  created_at: string
  company: string
  phone: string
  address: string
  city: string
  state: string
  website: string
  talking_points: string
  status: string
}

const STATUS_OPTIONS = ['new', 'called', 'not-interested', 'follow-up', 'won']

export default function CallsPage() {
  const [calls, setCalls] = useState<CallItem[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  async function load() {
    setLoading(true)
    const res = await fetch('/api/calls')
    const data = await res.json()
    setCalls((data.calls ?? []).filter((c: CallItem) => c.company))
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function updateStatus(rowIndex: number, status: string) {
    setSaving(rowIndex)
    await fetch('/api/calls', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row: rowIndex + 1, status }),
    })
    setCalls((prev) =>
      prev.map((c, i) => (i === rowIndex ? { ...c, status } : c))
    )
    setSaving(null)
  }

  if (loading) return <div className="text-gray-400 mt-8">Loading call list…</div>

  const active = calls.filter((c) => !c.status || c.status === 'new' || c.status === 'follow-up')
  const done = calls.filter((c) => c.status && c.status !== 'new' && c.status !== 'follow-up')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Call List</h1>
        <p className="text-sm text-gray-500 mt-1">
          Leads with no email found. Call them directly using the talking points below.
        </p>
      </div>

      {active.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 text-gray-400 text-sm">
          No active call leads right now.
        </div>
      )}

      <div className="space-y-3">
        {active.map((c) => {
          const realIndex = calls.indexOf(c)
          const isOpen = expanded === realIndex
          const points = c.talking_points
            ? c.talking_points.split(/\n|•/).map((p) => p.trim()).filter(Boolean)
            : []

          return (
            <div key={realIndex} className="bg-white rounded-xl border border-gray-100 shadow-sm">
              <button
                className="w-full text-left px-5 py-4 flex items-center gap-3"
                onClick={() => setExpanded(isOpen ? null : realIndex)}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900">{c.company}</div>
                  <div className="text-sm text-gray-500">
                    {c.phone}{c.city ? ` · ${c.city}, ${c.state}` : ''}
                  </div>
                </div>
                <StatusBadge status={c.status || 'new'} />
                <span className="text-gray-400 text-xs">{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && (
                <div className="border-t border-gray-50 px-5 py-4 space-y-4">
                  <div className="grid sm:grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Phone</div>
                      <a href={`tel:${c.phone}`} className="font-medium text-brand-600 hover:underline">
                        {c.phone}
                      </a>
                    </div>
                    {c.address && (
                      <div>
                        <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Address</div>
                        <div className="text-gray-700">{c.address}</div>
                      </div>
                    )}
                    {c.website && (
                      <div>
                        <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Website</div>
                        <a href={c.website} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline truncate block">
                          {c.website}
                        </a>
                      </div>
                    )}
                  </div>

                  {points.length > 0 && (
                    <div>
                      <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">Talking Points</div>
                      <ul className="space-y-1.5">
                        {points.map((p, pi) => (
                          <li key={pi} className="flex items-start gap-2 text-sm text-gray-700">
                            <span className="text-brand-500 mt-0.5">•</span>
                            {p}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div>
                    <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">Update Status</div>
                    <div className="flex flex-wrap gap-2">
                      {STATUS_OPTIONS.map((s) => (
                        <button
                          key={s}
                          disabled={saving === realIndex}
                          onClick={() => updateStatus(realIndex, s)}
                          className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50 ${
                            (c.status || 'new') === s
                              ? 'bg-brand-500 text-white border-brand-500'
                              : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                          }`}
                        >
                          {saving === realIndex ? '…' : s}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {done.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm text-gray-400 hover:text-gray-600 select-none">
            Show {done.length} completed call{done.length !== 1 ? 's' : ''}
          </summary>
          <div className="mt-3 space-y-2">
            {done.map((c) => {
              const realIndex = calls.indexOf(c)
              return (
                <div key={realIndex} className="bg-white rounded-xl border border-gray-100 shadow-sm px-5 py-3 flex items-center gap-3 opacity-60">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{c.company}</div>
                    <div className="text-xs text-gray-400">{c.phone}</div>
                  </div>
                  <StatusBadge status={c.status} />
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
    new: 'bg-blue-100 text-blue-700',
    called: 'bg-green-100 text-green-700',
    'not-interested': 'bg-red-100 text-red-500',
    'follow-up': 'bg-yellow-100 text-yellow-700',
    won: 'bg-purple-100 text-purple-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}
