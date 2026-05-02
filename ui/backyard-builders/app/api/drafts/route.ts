import { NextResponse } from 'next/server'
import { readRange, updateCell, rowsToObjects } from '@/lib/sheets'

// Drafts worksheet columns (1-indexed for Sheets A1 notation):
// A=created_at B=to C=subject D=body E=list_unsubscribe F=status
const RANGE = 'Drafts!A2:F'
const HEADERS = ['created_at', 'to', 'subject', 'body', 'list_unsubscribe', 'status']
const STATUS_COL = 'F' // column for status

export async function GET() {
  try {
    const rows = await readRange(RANGE)
    const drafts = rowsToObjects<{
      created_at: string
      to: string
      subject: string
      body: string
      list_unsubscribe: string
      status: string
    }>(HEADERS, rows)
    return NextResponse.json({ drafts })
  } catch (err) {
    console.error(err)
    return NextResponse.json({ error: 'Failed to read sheet' }, { status: 500 })
  }
}

// PATCH /api/drafts  body: { row: number (1-based data row), status: string }
export async function PATCH(req: Request) {
  try {
    const { row, status } = await req.json() as { row: number; status: string }
    // row 1 = header row, data rows start at 2
    const cellRange = `Drafts!${STATUS_COL}${row + 1}`
    await updateCell(cellRange, status)
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error(err)
    return NextResponse.json({ error: 'Failed to update sheet' }, { status: 500 })
  }
}
