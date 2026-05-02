import type { Metadata } from 'next'
import './globals.css'
import Nav from '@/components/Nav'

export const metadata: Metadata = {
  title: 'Backyard Builders — Blufire',
  description: 'Lead outreach dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <Nav />
        <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  )
}
