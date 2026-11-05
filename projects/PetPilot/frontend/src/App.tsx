import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  Bell,
  CalendarDays,
  Camera,
  ChevronDown,
  FileText,
  Image,
  Inbox,
  ListChecks,
  Maximize2,
  MessageCircle,
  Minimize2,
  PawPrint,
  Plus,
  X,
} from 'lucide-react'
import {
  api,
  apiMessageForm,
  type CareSummary,
  type Fact,
  type Held,
  type Msg,
  type Pet,
  type Reminder,
  type WeeklyReview,
} from './api'

type View = 'chat' | 'records' | 'held' | 'reminders' | 'care' | 'weekly'

const VIEWS: { key: View; label: string; icon: typeof Bell }[] = [
  { key: 'chat', label: '对话', icon: MessageCircle },
  { key: 'records', label: '记录', icon: ListChecks },
  { key: 'held', label: '挂起', icon: Inbox },
  { key: 'reminders', label: '提醒', icon: Bell },
  { key: 'care', label: '摘要', icon: FileText },
  { key: 'weekly', label: '周回顾', icon: CalendarDays },
]

type DraftPhoto = { id: string; file: File; url: string }

function SoundWaveIcon({ size = 20 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <circle cx="8" cy="12" r="2.2" fill="currentColor" stroke="none" />
      <path d="M12.5 8.5a5 5 0 0 1 0 7" />
      <path d="M15.5 6a9 9 0 0 1 0 12" />
    </svg>
  )
}

function PhotoImg({ id, onPreview }: { id: number; onPreview?: () => void }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let alive = true
    const token = localStorage.getItem('petpilot_token') || ''
    fetch(`/api/photos/${id}/file`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => alive && setUrl(URL.createObjectURL(b)))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [id])
  if (!url) return <div className="w-20 h-20 bg-subtle rounded-control shrink-0" />
  return <img src={url} alt="" onClick={onPreview} className="w-20 h-20 object-cover rounded-control cursor-zoom-in shrink-0 border border-black/5" />
}

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
  const [cares, setCares] = useState<CareSummary[]>([])
  const [weeklies, setWeeklies] = useState<WeeklyReview[]>([])
  const [text, setText] = useState('')
  const [draftPhotos, setDraftPhotos] = useState<DraftPhoto[]>([])
  const [expanded, setExpanded] = useState(false)
  const [showPlus, setShowPlus] = useState(false)
  const [sending, setSending] = useState(false)
  const [listening, setListening] = useState(false)
  const [err, setErr] = useState('')
  const [atBottom, setAtBottom] = useState(true)
  const [inputFocused, setInputFocused] = useState(false)
  const [needsExpand, setNeedsExpand] = useState(false)
  const [fullExpand, setFullExpand] = useState(false)
  const [fullExpandOpen, setFullExpandOpen] = useState(false)
  const [preview, setPreview] = useState<{ url: string; rect?: { top: number; left: number; width: number; height: number }; open: boolean } | null>(null)

  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const mainRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<any>(null)

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

  useEffect(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (!SR) return
    const rec = new SR()
    rec.lang = 'zh-CN'
    rec.continuous = true
    rec.interimResults = false
    rec.onresult = (e: any) => {
      const t = Array.from(e.results).map((r: any) => r[0]?.transcript || '').join('')
      if (t) setText((prev) => (prev ? prev + t : t))
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => {
      setListening(false)
      alert('语音识别不可用（需 HTTPS 或支持的浏览器），请用文字输入')
    }
    recognitionRef.current = rec
  }, [])

  function startListening() {
    const rec = recognitionRef.current
    if (!rec) {
      alert('语音识别不可用（需 HTTPS 或支持的浏览器），请用文字输入')
      return
    }
    try {
      setListening(true)
      rec.start()
    } catch {
      setListening(false)
    }
  }
  function stopListening() {
    const rec = recognitionRef.current
    if (!rec || !listening) return
    try {
      rec.stop()
    } catch {
      /* ignore */
    }
  }

  async function refresh(v: View) {
    try {
      if (v === 'records') setFacts((await api('/facts')).facts)
      else if (v === 'held') setHeld((await api('/held')).held_segments)
      else if (v === 'reminders') setReminders((await api('/reminders')).reminders)
      else if (v === 'care') setCares((await api('/care-summaries')).care_summaries)
      else if (v === 'weekly') setWeeklies((await api('/weekly-reviews')).weekly_reviews)
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

  function addFiles(list: FileList | null) {
    if (!list || list.length === 0) return
    const files = Array.from(list)
    const remain = 5 - draftPhotos.length
    if (remain <= 0) {
      alert('每条消息最多 5 张')
      return
    }
    if (files.length > remain) {
      alert(`这条消息还能加 ${remain} 张`)
    }
    const add = files.slice(0, remain)
    setDraftPhotos((prev) => [
      ...prev,
      ...add.map((f) => ({ id: `${Date.now()}-${Math.random()}`, file: f, url: URL.createObjectURL(f) })),
    ])
    setExpanded(true)
    setShowPlus(false)
  }

  function removeDraftPhoto(id: string) {
    setDraftPhotos((prev) => prev.filter((p) => p.id !== id))
  }

  async function send() {
    const t = text.trim()
    if ((!t && draftPhotos.length === 0) || sending) return
    setSending(true)
    setErr('')
    const files = draftPhotos.map((p) => p.file)
    const tmpPhotos = draftPhotos.map((p) => ({ id: 0, filename: p.file.name, pet_id: null, url: p.url }))
    setMessages((prev) => [
      ...prev,
      { id: -Date.now(), role: 'user', content: t || '[图片]', photos: tmpPhotos },
      { id: -Date.now() - 1, role: 'assistant', content: '正在思考…', photos: [] },
    ])
    setText('')
    setDraftPhotos([])
    setExpanded(false)
    setShowPlus(false)
    try {
      await apiMessageForm(t, files)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message || '发送失败')
    } finally {
      setSending(false)
      await load()
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

  function onMainScroll() {
    const el = mainRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 60)
  }

  useEffect(() => {
    if (atBottom) scrollToBottom()
  }, [messages, atBottom])

  // 展开时自动聚焦唤起键盘（#2）
  useEffect(() => {
    if (expanded) taRef.current?.focus()
  }, [expanded])

  // 输入框自适应高度：最多 5 行（120px），超出显示展开按钮
  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    const h = el.scrollHeight
    el.style.height = Math.min(h, 120) + 'px'
    setNeedsExpand(h > 122)
  }, [text, expanded, fullExpand, view])

  // 回到聊天页/消息变化后，按真实滚动位置更新 ↓（#10）
  useEffect(() => {
    if (view === 'chat') {
      const el = mainRef.current
      if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 60)
    }
  }, [view, messages])

  function scrollToBottom(smooth = false) {
    const el = mainRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }

  function openFullExpand() {
    setFullExpandOpen(false)
    setFullExpand(true)
    requestAnimationFrame(() => requestAnimationFrame(() => setFullExpandOpen(true)))
  }

  function closeFullExpand() {
    setFullExpandOpen(false)
    setTimeout(() => setFullExpand(false), 300)
  }

  function openPreview(url: string, el?: HTMLElement) {
    const r = el?.getBoundingClientRect()
    setPreview({ url, rect: r ? { top: r.top, left: r.left, width: r.width, height: r.height } : undefined, open: false })
    requestAnimationFrame(() => requestAnimationFrame(() => setPreview((p) => (p ? { ...p, open: true } : p))))
  }

  function closePreview() {
    setPreview((p) => (p ? { ...p, open: false } : p))
    setTimeout(() => setPreview(null), 300)
  }

  async function previewSentPhoto(id: number) {
    const token = localStorage.getItem('petpilot_token') || ''
    const r = await fetch(`/api/photos/${id}/file`, { headers: { Authorization: `Bearer ${token}` } })
    if (r.ok) openPreview(URL.createObjectURL(await r.blob()))
  }

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />

  return (
    <div className="h-dvh flex flex-col overflow-hidden max-w-[760px] mx-auto px-4 sm:px-6 relative">
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

      <div className="relative flex-1 min-h-0">
        <main ref={mainRef} onScroll={onMainScroll} onClick={() => { if (expanded && !text.trim() && draftPhotos.length === 0) { setExpanded(false); setShowPlus(false) } }} className="h-full py-4 overflow-y-auto">
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
                <div key={m.id} className="space-y-2">
                  {(m.photos && m.photos.length > 0) && (
                    <div className="flex justify-end">
                      <div className="max-w-[85%] flex gap-2 overflow-x-auto">
                        {m.photos.map((ph, i) => (
                          ph.url
                            ? <img key={i} src={ph.url} alt="" onClick={(e) => openPreview(ph.url!, e.currentTarget)} className="w-20 h-20 object-cover rounded-control cursor-zoom-in shrink-0 border border-black/5" />
                            : <PhotoImg key={i} id={ph.id} onPreview={() => previewSentPhoto(ph.id)} />
                        ))}
                      </div>
                    </div>
                  )}
                  {m.content !== '[图片]' && (
                    <div className="flex justify-end">
                      <div className="max-w-[85%] bg-user-bg text-user-text rounded-bubble rounded-br-md px-4 py-3 text-[16px] leading-[1.65]">
                        {m.content}
                      </div>
                    </div>
                  )}
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
            {err && <p className="text-[13px] text-red-500">{err}</p>}
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
      </main>
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-b from-transparent to-canvas" />
      </div>

      {view === 'chat' && (
        <footer className="bg-canvas pb-3 pt-1 shrink-0">
          {!atBottom && !inputFocused && (
            <div className="flex justify-center mb-2">
              <button
                onClick={() => scrollToBottom(true)}
                aria-label="回到底部"
                className="w-9 h-9 rounded-full bg-surface shadow-composer flex items-center justify-center text-ink"
              >
                <ChevronDown size={18} />
              </button>
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />

          {!expanded ? (
            <div
              onClick={() => { setExpanded(true); setTimeout(() => taRef.current?.focus(), 0) }}
              className="flex items-center gap-2 bg-surface rounded-composer shadow-composer p-1.5 cursor-text"
            >
              <button
                onPointerDown={(e) => { e.preventDefault(); startListening() }}
                onPointerUp={stopListening}
                onPointerLeave={stopListening}
                aria-label="按住说话"
                className={`w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 ${listening ? 'bg-accent text-white' : 'bg-subtle text-ink'}`}
              >
                <SoundWaveIcon />
              </button>
              <span className="flex-1 px-1 text-[16px] text-muted leading-[40px]">发消息或按住说话…</span>
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={(e) => { e.stopPropagation(); setShowPlus((v) => !v) }}
                aria-label="添加"
                className="w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 text-ink"
              >
                <Plus size={22} />
              </button>
            </div>
          ) : (
            <div className="relative bg-surface rounded-composer shadow-composer p-2">
              {draftPhotos.length > 0 && (
                <div className="flex gap-2 pb-2 px-1">
                  {draftPhotos.map((p) => (
                    <div key={p.id} className="relative w-[calc((100%-32px)/5)] aspect-square shrink-0">
                      <img src={p.url} alt="" onClick={(e) => openPreview(p.url, e.currentTarget)} className="w-full h-full object-cover rounded-control cursor-zoom-in" />
                      <button
                        onClick={() => removeDraftPhoto(p.id)}
                        aria-label="移除照片"
                        className="absolute top-1 right-1 w-5 h-5 rounded-full bg-ink/40 text-white flex items-center justify-center"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="relative py-2">
                <textarea
                  ref={taRef}
                  className={`w-full bg-transparent px-1 text-[16px] leading-6 text-ink resize-none focus:outline-none overflow-y-auto ${needsExpand ? 'pr-10' : ''}`}
                  rows={1}
                  placeholder="说说今天的变化…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onFocus={() => setInputFocused(true)}
                  onBlur={() => {
                    setInputFocused(false)
                    if (!text.trim() && draftPhotos.length === 0) setExpanded(false)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      send()
                    }
                  }}
                />
                {needsExpand && !fullExpand && (
                  <button onClick={openFullExpand} aria-label="展开" className="absolute top-2 right-1 w-8 h-8 flex items-center justify-center text-[#a3a3a3]">
                    <Maximize2 size={18} />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onPointerDown={(e) => { e.preventDefault(); startListening() }}
                  onPointerUp={stopListening}
                  onPointerLeave={stopListening}
                  aria-label="按住说话"
                  className={`w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 ${listening ? 'bg-accent text-white' : 'bg-subtle text-ink'}`}
                >
                  <SoundWaveIcon />
                </button>
                <div className="flex-1" />
                <button onMouseDown={(e) => e.preventDefault()} onClick={() => setShowPlus((v) => !v)} aria-label="添加" className="w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 text-ink">
                  <Plus size={22} />
                </button>
                <button
                  onClick={send}
                  disabled={sending || (!text.trim() && draftPhotos.length === 0)}
                  aria-label="发送"
                  className="w-[40px] h-[40px] rounded-full flex items-center justify-center shrink-0 bg-accent text-white hover:bg-accent-hover disabled:bg-subtle disabled:text-muted"
                >
                  <ArrowUp size={20} />
                </button>
              </div>
            </div>
          )}
        </footer>
      )}

      {showPlus && (
        <div className="fixed inset-0 z-50" onClick={() => setShowPlus(false)}>
          <div className="absolute inset-0 bg-ink/40" />
          <div className="absolute bottom-0 left-0 right-0 mx-auto max-w-[760px] bg-surface rounded-t-2xl p-4 pb-8" onClick={(e) => e.stopPropagation()}>
            <div className="flex gap-3">
              <button onClick={() => cameraRef.current?.click()} className="flex-1 flex flex-col items-center gap-2 py-5 rounded-control bg-subtle text-ink">
                <Camera size={24} />
                <span className="text-[15px]">拍照</span>
              </button>
              <button onClick={() => fileRef.current?.click()} className="flex-1 flex flex-col items-center gap-2 py-5 rounded-control bg-subtle text-ink">
                <Image size={24} />
                <span className="text-[15px]">照片</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {preview && (() => {
        const rect = preview.rect
        const scale = rect && !preview.open ? Math.max(rect.width / window.innerWidth, 0.05) : 1
        const tx = rect && !preview.open ? rect.left + rect.width / 2 - window.innerWidth / 2 : 0
        const ty = rect && !preview.open ? rect.top + rect.height / 2 - window.innerHeight / 2 : 0
        return (
          <div
            className={`fixed inset-0 z-[60] bg-black transition-opacity duration-300 ${preview.open ? 'opacity-100' : 'opacity-0'}`}
            onClick={closePreview}
          >
            <img
              src={preview.url}
              alt=""
              className="fixed left-1/2 top-1/2 max-w-[92vw] max-h-[92vh] object-contain transition-transform duration-300 ease-out"
              style={{ transform: `translate(calc(-50% + ${tx}px), calc(-50% + ${ty}px)) scale(${scale})` }}
            />
          </div>
        )
      })()}

      {fullExpand && (
        <div className={`fixed inset-0 z-[55] bg-canvas flex flex-col transition-all duration-300 ease-out ${fullExpandOpen ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}>
          <div className="flex items-center justify-end h-[56px] px-4 shrink-0">
            <button onClick={closeFullExpand} aria-label="收起" className="w-10 h-10 flex items-center justify-center text-[#a3a3a3]">
              <Minimize2 size={20} />
            </button>
          </div>
          <textarea
            autoFocus
            className="flex-1 w-full bg-transparent px-4 py-2 text-[16px] leading-[1.65] text-ink resize-none focus:outline-none"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="说说今天的变化…"
          />
        </div>
      )}

      <nav className={`bg-canvas pb-2 pt-2 shrink-0 flex justify-around ${inputFocused ? 'hidden' : ''}`}>
        {VIEWS.map((v) => {
          const Icon = v.icon
          const active = view === v.key
          return (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              className={`flex flex-col items-center gap-0.5 px-3 py-1 min-w-[52px] text-[12px] ${active ? 'text-accent' : 'text-muted'}`}
            >
              <Icon size={20} strokeWidth={1.75} fill={active ? 'currentColor' : 'none'} />
              {v.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

export default App
