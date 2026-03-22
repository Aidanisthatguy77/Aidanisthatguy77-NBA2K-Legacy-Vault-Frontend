import { FormEvent, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { Link, Route, Routes } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const TOKEN_KEY = 'vault_admin_token'

type AdminTab =
  | 'Dashboard'
  | 'Content'
  | 'Games'
  | 'Community'
  | 'Creator'
  | 'Health'
  | 'Doctor'
  | 'Comments'
  | 'Clips'
  | 'Proof'
  | 'Mockups'
  | 'Votes'
  | 'Social Feed'
  | 'Deploy'
  | 'Editor'
  | 'System Log'
  | 'Code Export'
  | 'Suggestions'
  | 'Mission Control'

const TABS: AdminTab[] = [
  'Dashboard',
  'Content',
  'Games',
  'Community',
  'Creator',
  'Health',
  'Doctor',
  'Suggestions',
  'Comments',
  'Clips',
  'Proof',
  'Mockups',
  'Votes',
  'Social Feed',
  'Deploy',
  'Editor',
  'System Log',
  'Code Export',
  'Mission Control',
]

function HomePage() {
  const [headline, setHeadline] = useState('NBA 2K Legacy Vault')

  useEffect(() => {
    axios
      .get(`${API_BASE}/api/content/hero_headline`)
      .then((res) => setHeadline(res.data?.value || 'NBA 2K Legacy Vault'))
      .catch(() => undefined)
  }, [])

  return (
    <main className="container">
      <h1>{headline}</h1>
      <p>Legacy Vault public site is live.</p>
    </main>
  )
}

function AdminPage() {
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || '')
  const [password, setPassword] = useState('')
  const [activeTab, setActiveTab] = useState<AdminTab>('Dashboard')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [content, setContent] = useState<Record<string, string>>({})
  const [contentKey, setContentKey] = useState('hero_headline')
  const [contentValue, setContentValue] = useState('')

  const [games, setGames] = useState<any[]>([])
  const [gameForm, setGameForm] = useState<any>({
    title: '',
    year: '',
    cover_image: '',
    hook_text: '',
    cover_athletes: '',
    description: '',
    youtube_embed: '',
    order: 0,
    is_active: true,
  })
  const [editingGameId, setEditingGameId] = useState<string | null>(null)

  const [communityPosts, setCommunityPosts] = useState<any[]>([])
  const [communityForm, setCommunityForm] = useState<any>({
    platform: 'twitter',
    author_name: '',
    author_handle: '',
    content: '',
    post_url: '',
    screenshot_url: '',
    order: 0,
  })

  const [creators, setCreators] = useState<any[]>([])
  const [healthChecks, setHealthChecks] = useState<any[]>([])
  const [doctorReport, setDoctorReport] = useState<any>(null)
  const [doctorProblem, setDoctorProblem] = useState('')
  const [genericData, setGenericData] = useState<any>(null)
  const [missionMessage, setMissionMessage] = useState('')
  const [missionExecute, setMissionExecute] = useState(false)
  const [missionConfirmAll, setMissionConfirmAll] = useState(false)
  const [missionResult, setMissionResult] = useState<any>(null)

  const client = useMemo(
    () =>
      axios.create({
        baseURL: API_BASE,
        headers: token ? { 'x-admin-token': token } : {},
      }),
    [token],
  )

  const login = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await axios.post(`${API_BASE}/api/admin/login`, { password })
      localStorage.setItem(TOKEN_KEY, res.data.token)
      setToken(res.data.token)
      setPassword('')
    } catch {
      setError('Invalid password')
    }
  }

  const loadTab = async (tab: AdminTab) => {
    setActiveTab(tab)
    setLoading(true)
    setError('')
    try {
      if (tab === 'Content') {
        const res = await client.get('/api/content')
        setContent(res.data || {})
      } else if (tab === 'Games') {
        const res = await client.get('/api/games/all')
        setGames(res.data || [])
      } else if (tab === 'Community') {
        const res = await client.get('/api/community-posts')
        setCommunityPosts(res.data || [])
      } else if (tab === 'Creator') {
        const res = await client.get('/api/creator-submissions')
        setCreators(res.data || [])
      } else if (tab === 'Health') {
        const [health, doctor] = await Promise.all([
          client.get('/api/admin/health'),
          client.get('/api/admin/doctor/diagnostic'),
        ])
        setHealthChecks(health.data || [])
        setDoctorReport(doctor.data || null)
      } else if (tab === 'Doctor') {
        const report = await client.get('/api/admin/doctor/diagnostic')
        setDoctorReport(report.data || null)
      } else if (tab === 'Dashboard') {
        const [health, suggestions] = await Promise.all([
          client.get('/api/admin/health'),
          client.get('/api/admin/suggestions'),
        ])
        setGenericData({ health: health.data, suggestions: suggestions.data })
      } else if (tab === 'Suggestions') {
        const r = await client.get('/api/admin/suggestions')
        setGenericData(r.data)
      } else if (tab === 'Comments') {
        const r = await client.get('/api/comments')
        setGenericData(r.data)
      } else if (tab === 'Clips') {
        const r = await client.get('/api/clips')
        setGenericData(r.data)
      } else if (tab === 'Proof') {
        const r = await client.get('/api/proof')
        setGenericData(r.data)
      } else if (tab === 'Mockups') {
        const r = await client.get('/api/mockups')
        setGenericData(r.data)
      } else if (tab === 'Votes') {
        const r = await client.get('/api/votes')
        setGenericData(r.data)
      } else if (tab === 'Social Feed') {
        const r = await client.get('/api/social-feed')
        setGenericData(r.data)
      } else if (tab === 'Deploy') {
        const [config, history] = await Promise.all([
          client.get('/api/admin/deploy/config'),
          client.get('/api/admin/deploy/history'),
        ])
        setGenericData({ config: config.data, history: history.data, note: 'Deploy actions may require external tokens.' })
      } else if (tab === 'Editor') {
        const [tree, backups] = await Promise.all([
          client.get('/api/admin/editor/tree'),
          client.get('/api/admin/editor/backups'),
        ])
        setGenericData({ tree: tree.data, backups: backups.data })
      } else if (tab === 'System Log') {
        const r = await client.get('/api/admin/system-log')
        setGenericData(r.data)
      } else if (tab === 'Code Export') {
        const r = await client.get('/api/admin/code/files')
        setGenericData(r.data)
      } else if (tab === 'Mission Control') {
        setMissionResult(null)
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed loading tab')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) loadTab(activeTab).catch(() => undefined)
  }, [token])

  const saveContent = async (e: FormEvent) => {
    e.preventDefault()
    await client.post('/api/content', { key: contentKey, value: contentValue })
    await loadTab('Content')
  }

  const startEditGame = (g: any) => {
    setEditingGameId(g.id)
    setGameForm({ ...g })
  }

  const submitGame = async (e: FormEvent) => {
    e.preventDefault()
    if (editingGameId) {
      await client.put(`/api/games/${editingGameId}`, gameForm)
    } else {
      await client.post('/api/games', gameForm)
    }
    setEditingGameId(null)
    setGameForm({ title: '', year: '', cover_image: '', hook_text: '', cover_athletes: '', description: '', youtube_embed: '', order: 0, is_active: true })
    await loadTab('Games')
  }

  const deleteGame = async (id: string) => {
    await client.delete(`/api/games/${id}`)
    await loadTab('Games')
  }

  const submitCommunity = async (e: FormEvent) => {
    e.preventDefault()
    await client.post('/api/community-posts', communityForm)
    setCommunityForm({ platform: 'twitter', author_name: '', author_handle: '', content: '', post_url: '', screenshot_url: '', order: 0 })
    await loadTab('Community')
  }

  const deleteCommunity = async (id: string) => {
    await client.delete(`/api/community-posts/${id}`)
    await loadTab('Community')
  }

  const updateCreatorStatus = async (id: string, status: 'approved' | 'rejected' | 'pending') => {
    await client.put(`/api/creator-submissions/${id}?status=${status}`)
    await loadTab('Creator')
  }

  const triggerHealthCheck = async () => {
    await client.post('/api/admin/health/check')
    await loadTab('Health')
  }

  const runDoctorSolve = async () => {
    const res = await client.post('/api/admin/doctor/solve', { problem: doctorProblem })
    setGenericData(res.data)
  }

  const runDoctorReset = async () => {
    const res = await client.post('/api/admin/doctor/reset')
    setGenericData(res.data)
    await loadTab('Doctor')
  }

  const runDoctorLockIn = async () => {
    const res = await client.post('/api/admin/doctor/lock-in')
    setGenericData(res.data)
  }

  const runSuggestionsGenerate = async () => {
    const res = await client.post('/api/admin/suggestions/generate')
    setGenericData(res.data)
    await loadTab('Suggestions')
  }

  const runEditorAgent = async () => {
    const res = await client.post('/api/admin/editor/agentic', { message: 'Review site structure and suggest improvements', history: [] })
    setGenericData(res.data)
  }

  const runMission = async () => {
    const message = missionMessage.trim()
    if (!message) {
      setError('Please describe your mission first.')
      return
    }
    setError('')
    const res = await client.post('/api/admin/operator-agent/chat', {
      message,
      execute: missionExecute,
      confirm_all: missionConfirmAll,
    })
    setMissionResult(res.data || null)
  }

  if (!token) {
    return (
      <main className="container">
        <h1>Admin Login</h1>
        <form onSubmit={login} className="stack">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Admin password" />
          <button type="submit">Login</button>
        </form>
        {error && <p className="error">{error}</p>}
      </main>
    )
  }

  return (
    <main className="container">
      <div className="top-nav">
        <strong>Phase C Admin</strong>
        <button onClick={() => { localStorage.removeItem(TOKEN_KEY); setToken('') }}>Logout</button>
      </div>

      <div className="tabs-grid">
        {TABS.map((tab) => (
          <button key={tab} className={tab === activeTab ? 'tab-active' : ''} onClick={() => loadTab(tab)}>
            {tab}
          </button>
        ))}
      </div>

      {loading && <p>Loading...</p>}
      {error && <p className="error">{error}</p>}

      {activeTab === 'Content' && (
        <section>
          <h2>Content Management</h2>
          <div className="split">
            <ul className="list">
              {Object.entries(content).map(([k, v]) => (
                <li key={k}>
                  <button onClick={() => { setContentKey(k); setContentValue(String(v ?? '')) }}>{k}</button>
                </li>
              ))}
            </ul>
            <form onSubmit={saveContent} className="stack">
              <input value={contentKey} onChange={(e) => setContentKey(e.target.value)} placeholder="content key" />
              <textarea rows={8} value={contentValue} onChange={(e) => setContentValue(e.target.value)} placeholder="content value" />
              <button type="submit">Save Content</button>
              <button type="button" onClick={() => client.post('/api/content/seed').then(() => loadTab('Content'))}>Seed Defaults</button>
            </form>
          </div>
        </section>
      )}

      {activeTab === 'Games' && (
        <section>
          <h2>Games Manager</h2>
          <form onSubmit={submitGame} className="stack">
            <input value={gameForm.title} onChange={(e) => setGameForm({ ...gameForm, title: e.target.value })} placeholder="Title" required />
            <input value={gameForm.year} onChange={(e) => setGameForm({ ...gameForm, year: e.target.value })} placeholder="Year" required />
            <input value={gameForm.cover_image} onChange={(e) => setGameForm({ ...gameForm, cover_image: e.target.value })} placeholder="Cover image URL" required />
            <input value={gameForm.hook_text} onChange={(e) => setGameForm({ ...gameForm, hook_text: e.target.value })} placeholder="Hook text" required />
            <input value={gameForm.cover_athletes} onChange={(e) => setGameForm({ ...gameForm, cover_athletes: e.target.value })} placeholder="Cover athletes" required />
            <textarea rows={4} value={gameForm.description} onChange={(e) => setGameForm({ ...gameForm, description: e.target.value })} placeholder="Description" required />
            <button type="submit">{editingGameId ? 'Update Game' : 'Create Game'}</button>
          </form>
          <ul className="list">
            {games.map((g) => (
              <li key={g.id}>
                <strong>{g.title}</strong> ({g.year})
                <div className="inline-actions">
                  <button onClick={() => startEditGame(g)}>Edit</button>
                  <button onClick={() => deleteGame(g.id)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {activeTab === 'Community' && (
        <section>
          <h2>Community Content</h2>
          <form onSubmit={submitCommunity} className="stack">
            <input value={communityForm.platform} onChange={(e) => setCommunityForm({ ...communityForm, platform: e.target.value })} placeholder="Platform" required />
            <input value={communityForm.author_name} onChange={(e) => setCommunityForm({ ...communityForm, author_name: e.target.value })} placeholder="Author name" required />
            <input value={communityForm.author_handle} onChange={(e) => setCommunityForm({ ...communityForm, author_handle: e.target.value })} placeholder="Author handle" required />
            <textarea rows={3} value={communityForm.content} onChange={(e) => setCommunityForm({ ...communityForm, content: e.target.value })} placeholder="Content" required />
            <button type="submit">Create Community Post</button>
          </form>
          <ul className="list">
            {communityPosts.map((p) => (
              <li key={p.id}>
                <strong>{p.author_name}</strong> ({p.platform})
                <p>{p.content}</p>
                <button onClick={() => deleteCommunity(p.id)}>Delete</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {activeTab === 'Creator' && (
        <section>
          <h2>Creator Submissions</h2>
          <ul className="list">
            {creators.map((c) => (
              <li key={c.id}>
                <strong>{c.name}</strong> - {c.platform} - <em>{c.status}</em>
                <div className="inline-actions">
                  <button onClick={() => updateCreatorStatus(c.id, 'approved')}>Approve</button>
                  <button onClick={() => updateCreatorStatus(c.id, 'rejected')}>Reject</button>
                  <button onClick={() => updateCreatorStatus(c.id, 'pending')}>Pending</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {activeTab === 'Health' && (
        <section>
          <h2>Health Operations</h2>
          <div className="inline-actions">
            <button onClick={triggerHealthCheck}>Trigger Health Check</button>
            <button onClick={() => loadTab('Health')}>Refresh</button>
          </div>
          <h3>Checks</h3>
          <pre className="json-dump">{JSON.stringify(healthChecks, null, 2)}</pre>
          <h3>Diagnostic</h3>
          <pre className="json-dump">{JSON.stringify(doctorReport, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'Doctor' && (
        <section>
          <h2>Doctor Controls</h2>
          <textarea rows={4} value={doctorProblem} onChange={(e) => setDoctorProblem(e.target.value)} placeholder="Describe issue" />
          <div className="inline-actions">
            <button onClick={() => loadTab('Doctor')}>Run Diagnostic</button>
            <button onClick={runDoctorSolve}>Solve</button>
            <button onClick={runDoctorReset}>Reset</button>
            <button onClick={runDoctorLockIn}>Lock-In Check</button>
          </div>
          <pre className="json-dump">{JSON.stringify(genericData ?? doctorReport, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'Suggestions' && (
        <section>
          <h2>Suggestions</h2>
          <button onClick={runSuggestionsGenerate}>Generate Suggestions</button>
          <pre className="json-dump">{JSON.stringify(genericData, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'Editor' && (
        <section>
          <h2>Editor Operations</h2>
          <div className="inline-actions">
            <button onClick={runEditorAgent}>Run Editor Agent</button>
            <button onClick={() => loadTab('Editor')}>Refresh Editor Data</button>
          </div>
          <pre className="json-dump">{JSON.stringify(genericData, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'Mission Control' && (
        <section>
          <h2>Mission Control / Operator Agent</h2>
          <p>Type one request that spans multiple tabs. Use plan mode first, then execute mode.</p>
          <textarea
            rows={5}
            value={missionMessage}
            onChange={(e) => setMissionMessage(e.target.value)}
            placeholder="Example: show dashboard counts, run health check, and run doctor diagnostic."
          />
          <label className="inline-actions">
            <input
              type="checkbox"
              checked={missionExecute}
              onChange={(e) => setMissionExecute(e.target.checked)}
            />
            Execute mode (applies changes)
          </label>
          <label className="inline-actions">
            <input
              type="checkbox"
              checked={missionConfirmAll}
              onChange={(e) => setMissionConfirmAll(e.target.checked)}
            />
            Confirm sensitive actions
          </label>
          <div className="inline-actions">
            <button onClick={runMission}>Run Mission</button>
            <button onClick={() => setMissionResult(null)}>Clear</button>
          </div>
          <pre className="json-dump">{JSON.stringify(missionResult, null, 2)}</pre>
        </section>
      )}

      {['Dashboard','Comments','Clips','Proof','Mockups','Votes','Social Feed','Deploy','System Log','Code Export'].includes(activeTab) && (
        <section>
          <h2>{activeTab}</h2>
          {activeTab === 'Deploy' && <p><strong>Note:</strong> Deploy actions require external credentials and are integration-dependent.</p>}
          {activeTab === 'Code Export' && (
            <div className="inline-actions">
              <a href={`${API_BASE}/api/admin/code/frontend.zip`} target="_blank" rel="noreferrer">Frontend Zip</a>
              <a href={`${API_BASE}/api/admin/code/backend.zip`} target="_blank" rel="noreferrer">Backend Zip</a>
              <a href={`${API_BASE}/api/admin/code/fullstack.zip`} target="_blank" rel="noreferrer">Fullstack Zip</a>
            </div>
          )}
          <pre className="json-dump">{JSON.stringify(genericData, null, 2)}</pre>
        </section>
      )}
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/admin" element={<AdminPage />} />
    </Routes>
  )
}
