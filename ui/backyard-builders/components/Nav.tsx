'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const links = [
  { href: '/', label: 'Dashboard' },
  { href: '/drafts', label: 'Drafts' },
  { href: '/calls', label: 'Call List' },
]

export default function Nav() {
  const path = usePathname()
  return (
    <nav className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-8 h-14">
        <span className="font-bold text-brand-600 text-lg tracking-tight">
          Backyard Builders
        </span>
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`text-sm font-medium transition-colors ${
              path === l.href
                ? 'text-brand-600 border-b-2 border-brand-500 pb-0.5'
                : 'text-gray-500 hover:text-gray-900'
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
