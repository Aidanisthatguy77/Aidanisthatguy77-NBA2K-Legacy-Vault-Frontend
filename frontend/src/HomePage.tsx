import { useEffect, useState } from 'react'
import axios from 'axios'
import { API_BASE } from './config'

function HomePage() {
  const [headline, setHeadline] = useState('THE NBA 2K LEGACY VAULT')

  useEffect(() => {
    axios
      .get(`${API_BASE}/api/content/hero_headline`)
      .then((res) => setHeadline(String(res.data?.value || 'THE NBA 2K LEGACY VAULT').toUpperCase()))
      .catch(() => undefined)
  }, [])

  return (
    <main className="vault-home">
      <header className="vault-topbar">
        <div className="vault-logo">2K Legacy Vault</div>
        <nav className="vault-nav">
          <a href="#home">Home</a>
          <a href="#games">The Games</a>
          <a href="#vault">The Vault</a>
          <a href="#community">Community</a>
        </nav>
      </header>

      <section className="vault-hero" id="home">
        <div className="vault-target" aria-hidden="true">
          <span className="vault-target-inner" />
        </div>
        <h1>{headline}</h1>
        <p className="vault-era">2K15 · 2K16 · 2K17 · 2K20 — All in one place.</p>
        <p className="vault-tagline">Persistent online. No resets. Ever.</p>

        <div className="vault-cta-row">
          <a className="vault-cta vault-cta-primary" href="#games">EXPLORE THE GAMES</a>
          <a className="vault-cta vault-cta-secondary" href="#vault">SEE THE VISION</a>
        </div>

        <div className="vault-social-row" aria-label="social links">
          <span>X</span>
          <span>IG</span>
          <span>TikTok</span>
        </div>
        <a className="vault-down" href="#games">⌄</a>
      </section>

      <section className="vault-panel" id="games">
        <h2>The Games</h2>
        <p>Legacy builds and servers for 2K15/16/17/20, curated in one place.</p>
      </section>
      <section className="vault-panel" id="vault">
        <h2>The Vault</h2>
        <p>Roadmap, archive, and preservation mission for online-first 2K history.</p>
      </section>
      <section className="vault-panel" id="community">
        <h2>Community</h2>
        <p>Creators, clips, comments, and proof that the audience is still here.</p>
      </section>

      <aside className="vault-assistant" aria-label="Vault AI assistant">
        <div className="vault-assistant-header">VAULT AI</div>
        <p>
          Hey! I&apos;m Vault AI — your 24/7 guide to the NBA 2K Legacy Vault concept. Ask me
          anything about how it works, the tech, or why this needs to happen.
        </p>
        <div className="vault-assistant-chips">
          <button type="button">What is the Legacy Vault?</button>
          <button type="button">How does licensing work?</button>
          <button type="button">Why build 2K&apos;s this way?</button>
        </div>
      </aside>
    </main>
  )
}


export default HomePage
