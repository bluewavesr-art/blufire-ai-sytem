import { readRange, rowsToObjects } from '@/lib/sheets'
import { formatDistanceToNow } from 'date-fns'
import Link from 'next/link'

interface Draft {
  created_at: string
  to: string
  subject: string
  status: string
}

interface CallItem {
  created_at: string
  company: string
  phone: string
  status: string
}

async function getDashboardData() {
  const [draftRows, callRows] = await Promise.all([
    readRange('Drafts!A2:F'),
    readRange('Call List!A2:I'),
  ])

  const drafts = rowsToObjects<Draft>(
    ['created_at', 'to', 'subject', 'body', 'list_unsubscribe', 'status'],
    draftRows,
  ).filter((d) => d.to)

  const calls = rowsToObjects<CallItem>(
    ['created_at', 'company', 'phone', 'address', 'city', 'state', 'website', 'talking_points', 'status'],
    callRows,
  ).filter((c) => c.company)

  const pendingDrafts = drafts.filter((d) => !d.status || d.status === 'pending')
  const sentDrafts = drafts.filter((d) => d.status === 'sent')
  const pendingCalls = calls.filter((c) => !c.status || c.status === 'new')
  const calledDone = calls.filter((c) => c.status === 'called')

  return { drafts, calls, pendingDrafts, sentDrafts, pendingCalls, calledDone }
}

function StatCard({
  label,
  value,
  sub,
  href,
  color = 'brand',
}: {
  label: string
  value: number
  sub?: string
  href?: string
  color?: 'brand' | 'green' | 'blue' | 'gray'
}) {
  const colorMap = {
    brand: 'bg-brand-500 text-white',
    green: 'bg-green-500 text-white',
    blue: 'bg-blue-500 text-white',
    gray: 'bg-gray-200 text-gray-700',
  }
  const card = (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col gap-1 hover:shadow-md transition-shadow">
      <div className={`text-3xl font-bold ${colorMap[color]} rounded-lg w-14 h-14 flex items-center justify-center`}>
        {value}
      </div>
      <div className="mt-3 font-semibold text-gray-800">{label}</div>
      {sub && <div className="text-xs text-gray-400">{sub}</div>}
    </div>
  )
  return href ? <Link href={href}>{card}</Link> : card
}

export const revalidate = 60

export default async function DashboardPage() {
  let data
  try {
    data = await getDashboardData()
  } catch {
    return (
      <div className="text-red-500 mt-8">
        Failed to load sheet data. Check that <code>GOOGLE_SERVICE_ACCOUNT_JSON</code> and{' '}
        <code>SHEET_ID</code> are set in your Vercel environment.
      </div>
    )
  }

  const { drafts, calls, pendingDrafts, sentDrafts, pendingCalls, calledDone } = data

  const recentDrafts = [...drafts]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5)

  const recentCalls = [...calls]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5)

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Backyard Builders · Blufire Autopilot</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pending Drafts" value={pendingDrafts.length} sub="awaiting review" href="/drafts" color="brand" />
        <StatCard label="Emails Sent" value={sentDrafts.length} sub="total" color="green" />
        <StatCard label="Calls Queued" value={pendingCalls.length} sub="new leads" href="/calls" color="blue" />
        <StatCard label="Calls Done" value={calledDone.length} sub="total" color="gray" />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-700">Recent Drafts</h2>
            <Link href="/drafts" className="text-xs text-brand-600 hover:underline">View all →</Link>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm divide-y divide-gray-50">
            {recentDrafts.length === 0 && (
              <p className="text-gray-400 text-sm p-4">No drafts yet. Leads run daily at 6 AM CST.</p>
            )}
            {recentDrafts.map((d, i) => (
              <div key={i} className="px-4 py-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{d.to}</div>
                  <div className="text-xs text-gray-400 truncate">{d.subject}</div>
                </div>
                <StatusBadge status={d.status || 'pending'} />
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-700">Recent Calls</h2>
            <Link href="/calls" className="text-xs text-brand-600 hover:underline">View all →</Link>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm divide-y divide-gray-50">
            {recentCalls.length === 0 && (
              <p className="text-gray-400 text-sm p-4">No call leads yet.</p>
            )}
            {recentCalls.map((c, i) => (
              <div key={i} className="px-4 py-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{c.company}</div>
                  <div className="text-xs text-gray-400">{c.phone}</div>
                </div>
                <StatusBadge status={c.status || 'new'} />
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-700',
    sent: 'bg-green-100 text-green-700',
    skipped: 'bg-gray-100 text-gray-500',
    new: 'bg-blue-100 text-blue-700',
    called: 'bg-green-100 text-green-700',
    'not-interested': 'bg-red-100 text-red-500',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${map[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}
