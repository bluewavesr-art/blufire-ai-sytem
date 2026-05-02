import { NextResponse } from 'next/server'
import { readRange, updateCell, rowsToObjects } from '@/lib/sheets'

// Call List worksheet columns:
// A=created_at B=company C=phone D=address E=city F=state G=website H=talking_points I=status
const RANGE = 'Call List!A2:I'
const HEADERS = ['created_at', 'company', 'phone', 'address', 'city', 'state', 'website', 'talking_points', 'status']
const STATUS_COL = 'I'

export async function GET() {
  try {
    const rows = await readRange(RANGE)
    const calls = rowsToObjects<{
      created_at: string
      company: string
      phone: string
      address: string
      city: string
      state: string
      website: string
      talking_points: string
      status: string
    }>(HEADERS, rows)
    return NextResponse.json({ calls })
  } catch (err) {
    console.error(err)
    return NextResponse.json({ error: 'Failed to read sheet' }, { status: 500 })
  }
}

// PATCH /api/calls  body: { row: number (1-based data row), status: string }
export async function PATCH(req: Request) {
  try {
    const { row, status } = await req.json() as { row: number; status: string }
    const cellRange = `Call List!${STATUS_COL}${row + 1}`
    await updateCell(cellRange, status)
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error(err)
    return NextResponse.json({ error: 'Failed to update sheet' }, { status: 500 })
  }
}
