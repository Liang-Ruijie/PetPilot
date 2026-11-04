import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  Bell,
  CalendarDays,
  ChevronDown,
  FileText,
  Image,
  Inbox,
  ListChecks,
  MessageCircle,
  PawPrint,
  Plus,
  X,
} from 'lucide-react'
import {
  api,
  apiForm,
  type CareSummary,
  type Fact,
  type Held,
  type Msg,
  type Pet,
  type Photo,
  type Reminder,
  type WeeklyReview,
} from './api'

type View = 'chat' | 'records' | 'held' | 'reminders' | 'photos' | 'care' | 'weekly'

const VIEWS: { key: View; label: string; icon: typeof Bell }[] = [
  { key: 'chat', label: '对话', icon: MessageCircle },
  { key: 'records', label: '记录', icon: ListChecks },
  { key: 'held', label: '挂起', icon: Inbox },
  { key: 'reminders', label: '提醒', icon: Bell },
  { key: 'photos', label: '照片', icon: Image },
  { key: 'care', label: '摘要', icon: FileText },
  { key: 'weekly', label: '周回顾', icon: CalendarDays },
]

function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [code, setCode] = useState('123456')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  async function submit() {
    setErr('')
    setLoading(true)
    try {
      const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ code }) })
      localStorage.setItem('petpilot_token', data.token)
      onLogin()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '登录失败')
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="min-h-dvh flex items-center justify-center p-4">
      <div className="w-full max-w-[360px]">
        <div className="flex items-center gap-2 mb-8">
          <PawPrint size={26} className="text-accent" />
          <span className="text-[20px] font-semibold text-ink">PetPilot</span>
        </div>
        <p className="text-[15px] text-secondary mb-6">猫主人的 Personal Agent</p>
        <input
          className="w-full h-[44px] rounded-control border border-line bg-surface px-4 text-[16px] text-ink focus:outline-none focus:ring-2 focus:ring-accent"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="验证码"
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        {err && <p className="mt-2 text-[13px] text-danger">{err}</p>}
        <button
          onClick={submit}
          disabled={loading}
          className="mt-3 w-full h-[44px] bg-accent text-white rounded-control text-[16px] font-medium hover:bg-accent-hover disabled:opacity-50"
        >
          {loading ? '登录中…' : '登录'}
        </button>
        <p className="mt-4 text-[12px] text-muted">测试模式：固定验证码 123456，仅用于合成体验空间。</p>
      </div>
    </div>
  )
}

function SectionTitle({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between py-2">
      <h2 className="text-[22px] font-semibold text-ink">{title}</h2>
      <button onClick={onClose} aria-label="返回对话" className="min-w-[44px] min-h-[44px] flex items-center justify-center text-secondary">
        <X size={20} />
      </button>
    </div>
  )
}

function App() {
  const [authed, setAuthed] = useState(!!localStorage.getItem('petpilot_token'))
  const [view, setView] = useState<View>('chat')
  const [pets, setPets] = useState<Pet[]>([])
  const [messages, setMessages] = useState<Msg[]>([])
  const [facts, setFacts] = useState<Fact[]>([])
  const [held, setHeld] = useState<Held[]>([])
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [photos, setPhotos] = useState<Photo[]>([])
  const [cares, setCares] = useState<CareSummary[]>([])
  const [weeklies, setWeeklies] = useState<WeeklyReview[]>([])
  const [text, setText] = useState('')
  const [photoPetId, setPhotoPetId] = useState<number | ''>('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState('')
  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const [p, m] = await Promise.all([api('/pets'), api('/messages')])
      setPets(p.pets)
      setMessages(m.messages)
    } catch {
      // 登录失效
    }
  }, [])

  useEffect(() => {
    if (authed) load()
  }, [authed, load])

  useEffect(() => {
    const onExpired = () => setAuthed(false)
    window.addEventListener('petpilot-auth-expired', onExpired)
    return () => window.removeEventListener('petpilot-auth-expired', onExpired)
  }, [])

  async function refresh(view: View) {
    try {
      if (view === 'records') setFacts((await api('/facts')).facts)
      else if (view === 'held') setHeld((await api('/held')).held_segments)
      else if (view === 'reminders') setReminders((await api('/reminders')).reminders)
      else if (view === 'photos') setPhotos((await api('/photos')).photos)
      else if (view === 'care') setCares((await api('/care-summaries')).care_summaries)
      else if (view === 'weekly') setWeeklies((await api('/weekly-reviews')).weekly_reviews)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '加载失败')
    }
  }

  useEffect(() => {
    refresh(view)
  }, [view])

  async function addPet() {
    const name = prompt('新猫的名字')
    if (!name) return
    try {
      await api('/pets', { method: 'POST', body: JSON.stringify({ name }) })
      load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '建猫失败')
    }
  }

  async function send() {
    const t = text.trim()
    if (!t || sending) return
    setSending(true)
    setErr('')
    setText('')
    try {
      await api('/messages', { method: 'POST', body: JSON.stringify({ text: t }) })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '发送失败')
    } finally {
      setSending(false)
      taRef.current?.focus()
    }
  }

  async function remAction(id: number, action: 'complete' | 'pause' | 'cancel') {
    await api(`/reminders/${id}/${action}`, { method: 'POST' })
    refresh('reminders')
  }

  async function fillReminderTime(id: number) {
    const t = prompt('提醒时间，比如：明天上午九点')
    if (!t) return
    try {
      await api(`/reminders/${id}/update`, { method: 'POST', body: JSON.stringify({ due_at: t }) })
      refresh('reminders')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '补时间失败')
    }
  }

  async function fillReminderPet(id: number) {
    const name = prompt('给哪只猫？')
    if (!name) return
    const pet = pets.find((p) => p.name === name.trim())
    if (!pet) {
      setErr('没有这只猫，请先建猫')
      return
    }
    try {
      await api(`/reminders/${id}/update`, { method: 'POST', body: JSON.stringify({ pet_id: pet.id }) })
      refresh('reminders')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '选猫失败')
    }
  }

  async function uploadPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setErr('')
    try {
      const desc = prompt('照片描述（可选）') || ''
      const fd = new FormData()
      fd.append('file', f)
      fd.append('description', desc)
      if (photoPetId !== '') fd.append('pet_id', String(photoPetId))
      await apiForm('/photos', fd)
      refresh('photos')
    } catch (err2: unknown) {
      setErr((err2 as { message?: string }).message || '上传失败')
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function simulateReply(id: number) {
    try {
      const data = await api(`/care-summaries/${id}/simulate-reply`, { method: 'POST' })
      setErr(data.reply)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '失败')
    }
  }

  async function genWeekly() {
    setErr('')
    try {
      await api('/weekly-review', { method: 'POST', body: JSON.stringify({}) })
      refresh('weekly')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '生成失败')
    }
  }

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />

  return (
    <div className="h-dvh flex flex-col overflow-hidden max-w-[760px] mx-auto px-4 sm:px-6">
      <header className="flex items-center justify-between h-[56px] shrink-0">
        <div className="flex items-center gap-2.5">
          <PawPrint size={26} className="text-accent" />
          <span className="text-[20px] font-semibold text-ink">PetPilot</span>
        </div>
        <button onClick={addPet} className="flex items-center gap-1 text-[14px] text-accent font-medium min-h-[44px] px-2">
          <Plus size={16} /> 建猫
        </button>
      </header>

      {pets.length > 0 && view === 'chat' && (
        <div className="flex gap-2 pb-3 overflow-x-auto shrink-0">
          {pets.map((p) => (
            <span key={p.id} className="shrink-0 inline-flex items-center h-[30px] px-3 rounded-full bg-surface border border-line text-[14px] text-ink">
              {p.name}
            </span>
          ))}
        </div>
      )}

      <main className="flex-1 py-4 overflow-y-auto">
        {view === 'chat' && (
          <div className="space-y-6">
            {messages.length === 0 && (
              <div className="pt-8 pb-4">
                <h2 className="text-[26px] font-semibold text-ink leading-snug">随手记一句猫的日常</h2>
                <p className="mt-2 text-[16px] text-secondary leading-relaxed">
                  我会自动分清是哪只猫、记住它，并在需要时提醒你。比如：明月今天吃了 26 克，贝塔有点拉稀。
                </p>
              </div>
            )}
            {messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] bg-user-bg text-user-text rounded-bubble rounded-br-md px-4 py-3 text-[16px] leading-[1.65]">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex justify-start">
                  <div className="max-w-full text-[16px] leading-[1.65] text-ink whitespace-pre-wrap">
                    <div className="flex items-center gap-1.5 mb-1">
                      <PawPrint size={14} className="text-muted" />
                      <span className="text-[12px] text-muted">PetPilot</span>
                    </div>
                    {m.content}
                  </div>
                </div>
              ),
            )}
          </div>
        )}

        {view === 'records' && (
          <div>
            <SectionTitle title="记录" onClose={() => setView('chat')} />
            {facts.length === 0 ? (
              <p className="text-[15px] text-secondary">暂无记录。</p>
            ) : (
              <div className="space-y-2">
                {facts.map((f) => (
                  <div key={f.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] text-ink">
                      <span className="text-secondary">「{f.pet_name}」</span>
                      {f.topic || '记录'}
                      {f.value != null ? ` ${f.value}${f.unit || ''}` : ''}
                    </div>
                    <div className="mt-1 text-[12px] text-muted">版本 v{f.version} · 出处：{f.quote}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {view === 'held' && (
          <div>
            <SectionTitle title="挂起" onClose={() => setView('chat')} />
            {held.length === 0 ? (
              <p className="text-[15px] text-secondary">暂无待归属的片段。建猫后，提到那只猫的片段会自动归过去。</p>
            ) : (
              <div className="space-y-2">
                {held.map((h) => (
                  <div key={h.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] text-ink">{h.quote}</div>
                    <div className="mt-1 text-[12px] text-muted">
                      {h.topic ? `${h.topic}${h.value != null ? ` ${h.value}${h.unit || ''}` : ''} · ` : ''}归属未知（建猫后自动补归属）
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {view === 'reminders' && (
          <div>
            <SectionTitle title="提醒" onClose={() => setView('chat')} />
            {reminders.length === 0 ? (
              <p className="text-[15px] text-secondary">暂无提醒。</p>
            ) : (
              <div className="space-y-2">
                {reminders.map((r) => (
                  <div key={r.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] text-ink">{r.quote}</div>
                    <div className="mt-1 text-[12px] text-muted">
                      {r.pet_name ? `「${r.pet_name}」 · ` : '待补对象 · '}
                      {r.due_at || '待补时间'} · {r.status === 'pending' ? (r.is_due ? '已到期 · 待跟进' : '待提醒') : r.status}
                    </div>
                    {r.status === 'pending' && (
                      <div className="mt-2 flex gap-2 flex-wrap">
                        {!r.due_at && <button onClick={() => fillReminderTime(r.id)} className="px-3 py-1.5 rounded-control bg-subtle text-ink text-[13px]">补时间</button>}
                        {!r.pet_name && <button onClick={() => fillReminderPet(r.id)} className="px-3 py-1.5 rounded-control bg-subtle text-ink text-[13px]">选猫</button>}
                        <button onClick={() => remAction(r.id, 'complete')} className="px-3 py-1.5 rounded-control bg-accent text-white text-[13px]">完成</button>
                        <button onClick={() => remAction(r.id, 'pause')} className="px-3 py-1.5 rounded-control bg-subtle text-ink text-[13px]">暂停</button>
                        <button onClick={() => remAction(r.id, 'cancel')} className="px-3 py-1.5 rounded-control bg-subtle text-ink text-[13px]">取消</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {view === 'photos' && (
          <div>
            <SectionTitle title="照片" onClose={() => setView('chat')} />
            <div className="flex items-center gap-2 mb-4">
              <div className="relative">
                <select
                  value={photoPetId}
                  onChange={(e) => setPhotoPetId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="h-[40px] pl-3 pr-8 rounded-control border border-line bg-surface text-[14px] text-ink appearance-none"
                >
                  <option value="">不指定猫</option>
                  {pets.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <ChevronDown size={16} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-muted" />
              </div>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={uploadPhoto} />
              <button onClick={() => fileRef.current?.click()} className="px-4 py-2 rounded-control bg-accent text-white text-[14px]">上传照片</button>
            </div>
            <div className="mt-4 space-y-2">
              {photos.length === 0 ? (
                <p className="text-[15px] text-secondary">暂无照片。</p>
              ) : (
                photos.map((p) => (
                  <div key={p.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] text-ink">{p.pet_name ? `「${p.pet_name}」` : ''} {p.filename}</div>
                    {p.description && <div className="mt-1 text-[13px] text-secondary">{p.description}</div>}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {view === 'care' && (
          <div>
            <SectionTitle title="就医摘要" onClose={() => setView('chat')} />
            {cares.length === 0 ? (
              <p className="text-[15px] text-secondary">暂无摘要。发一句"帮我整理就医摘要，先不要发"试试。</p>
            ) : (
              <div className="space-y-3">
                {cares.map((c) => (
                  <div key={c.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] font-medium text-ink">「{c.pet_name}」{c.title}{c.stale && <span className="ml-2 text-[12px] text-warning">（已过期，事实有更新）</span>}</div>
                    <p className="mt-2 text-[15px] leading-[1.65] text-ink whitespace-pre-wrap">{c.summary}</p>
                    <button onClick={() => simulateReply(c.id)} className="mt-3 px-3 py-1.5 rounded-control bg-subtle text-ink text-[13px]">模拟医院回复</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {view === 'weekly' && (
          <div>
            <SectionTitle title="周回顾" onClose={() => setView('chat')} />
            <button onClick={genWeekly} className="px-4 py-2 rounded-control bg-accent text-white text-[14px]">生成周回顾</button>
            <div className="mt-4 space-y-3">
              {weeklies.length === 0 ? (
                <p className="text-[15px] text-secondary">暂无周回顾。</p>
              ) : (
                weeklies.map((w) => (
                  <div key={w.id} className="bg-surface border border-line rounded-card p-4">
                    <div className="text-[15px] font-medium text-ink">「{w.pet_name}」{w.title}{w.stale && <span className="ml-2 text-[12px] text-warning">（已过期，事实有更新）</span>}</div>
                    <p className="mt-2 text-[15px] leading-[1.65] text-ink whitespace-pre-wrap">{w.summary}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {err && view !== 'chat' && (
          <div className="mt-3 bg-danger-bg text-danger text-[13px] rounded-card px-4 py-2.5 whitespace-pre-wrap">{err}</div>
        )}
      </main>

      {view === 'chat' && (
        <footer className="bg-canvas pb-3 pt-1 shrink-0">
          <div className="flex items-end gap-2 bg-surface border border-line rounded-composer shadow-composer p-1.5">
            <textarea
              ref={taRef}
              className="flex-1 bg-transparent px-3 py-2.5 text-[16px] text-ink resize-none focus:outline-none max-h-[160px]"
              rows={1}
              placeholder="说说今天的变化…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <button
              onClick={send}
              disabled={sending || !text.trim()}
              aria-label="发送"
              className="w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 bg-accent text-white hover:bg-accent-hover disabled:bg-subtle disabled:text-muted"
            >
              <ArrowUp size={20} />
            </button>
          </div>
        </footer>
      )}

      <nav className="bg-canvas border-t border-line pb-2 pt-2 shrink-0 flex justify-around">
        {VIEWS.map((v) => {
          const Icon = v.icon
          const active = view === v.key
          return (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              className={`flex flex-col items-center gap-0.5 px-3 py-1 min-w-[52px] text-[12px] ${active ? 'text-accent' : 'text-muted'}`}
            >
              <Icon size={20} strokeWidth={1.75} />
              {v.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

export default App
