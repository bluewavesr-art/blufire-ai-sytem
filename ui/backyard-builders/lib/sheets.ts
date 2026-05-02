import { google } from 'googleapis'

const SHEET_ID = process.env.SHEET_ID!

function getAuth() {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON!
  const creds = JSON.parse(raw)
  return new google.auth.GoogleAuth({
    credentials: creds,
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
  })
}

export async function getSheet() {
  const auth = getAuth()
  const sheets = google.sheets({ version: 'v4', auth })
  return { sheets, spreadsheetId: SHEET_ID }
}

export async function readRange(range: string): Promise<string[][]> {
  const { sheets, spreadsheetId } = await getSheet()
  const res = await sheets.spreadsheets.values.get({ spreadsheetId, range })
  return (res.data.values as string[][]) ?? []
}

export async function updateCell(range: string, value: string): Promise<void> {
  const { sheets, spreadsheetId } = await getSheet()
  await sheets.spreadsheets.values.update({
    spreadsheetId,
    range,
    valueInputOption: 'RAW',
    requestBody: { values: [[value]] },
  })
}

export function rowsToObjects<T>(headers: string[], rows: string[][]): T[] {
  return rows.map((row) => {
    const obj: Record<string, string> = {}
    headers.forEach((h, i) => { obj[h] = row[i] ?? '' })
    return obj as T
  })
}
