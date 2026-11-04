export type Pet = { id: number; name: string }
export type Msg = { id: number; role: 'user' | 'assistant'; content: string }
export type Fact = { id: number; pet_name: string; topic: string | null; value: number | null; unit: string | null; quote: string; version: number }
export type Reminder = { id: number; pet_name: string | null; quote: string; due_at: string | null; status: string; is_due: boolean }
export type Photo = { id: number; pet_name: string | null; filename: string; description: string }
export type CareSummary = { id: number; pet_name: string; title: string; summary: string }
export type WeeklyReview = { id: number; pet_name: string; title: string; summary: string }

const API = '/api'

function token() {
  return localStorage.getItem('petpilot_token') || ''
}

function handleAuthError() {
  localStorage.removeItem('petpilot_token')
  window.dispatchEvent(new Event('petpilot-auth-expired'))
}

export async function api(path: string, opts: RequestInit = {}) {
  const r = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token() ? { Authorization: 'Bearer ' + token() } : {}),
      ...(opts.headers || {}),
    },
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const err = data.error || { code: 'HTTP_ERROR', message: r.statusText }
    if (err.code === 'AUTH_REQUIRED') handleAuthError()
    throw err
  }
  return data
}

export async function apiForm(path: string, form: FormData) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: token() ? { Authorization: 'Bearer ' + token() } : {},
    body: form,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const err = data.error || { code: 'HTTP_ERROR', message: r.statusText }
    if (err.code === 'AUTH_REQUIRED') handleAuthError()
    throw err
  }
  return data
}
