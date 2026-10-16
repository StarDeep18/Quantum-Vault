import { useEffect } from 'react'
import type { Theme, HardwareStatus, VaultRecord } from '../types'
import { BrandMark, Icon } from './Icons'
import { ThemeToggle } from './ThemeToggle'
import { VaultScene } from './VaultSceneLazy'

interface LandingPageProps {
  theme: Theme
  hardware: HardwareStatus
  savedVault: VaultRecord | null
  onThemeChange: (theme: Theme) => void
  onCreate: () => void
  onOpen: () => void
}

export function LandingPage({ theme, hardware, savedVault, onThemeChange, onCreate, onOpen }: LandingPageProps) {
  useEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>('.landing-page .reveal-item'))
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach((item) => item.classList.add('reveal-visible'))
      return
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('reveal-visible')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.12 })
    items.forEach((item) => observer.observe(item))
    return () => observer.disconnect()
  }, [])

  return (
    <main className="landing-page">
      <header className="app-header landing-header">
        <a className="brand-lock" href="#top" aria-label="Quantum Vault home">
          <BrandMark size={31} /><span>QUANTUM <b>VAULT</b></span>
        </a>
        <nav className="landing-nav" aria-label="Main navigation">
          <a href="#method">THE METHOD</a>
          <a href="#security">SECURITY MODEL</a>
        </nav>
        <div className="header-actions">
          <ThemeToggle theme={theme} onChange={onThemeChange} />
          {savedVault ? (
            <button className="button button-outline header-open-button" type="button" onClick={onOpen}><Icon name="unlock" size={15} /> OPEN VAULT</button>
          ) : (
            <button className="button button-outline header-open-button" type="button" onClick={onCreate}>CREATE VAULT <Icon name="arrow-right" size={15} /></button>
          )}
        </div>
      </header>

      <section className="hero-section" id="top">
        <div className="hero-copy">
          <div className="bridge-label"><span className="bridge-dot" /> AFTER THE QUANTUM RANDOMNESS LAB <i /> SEPARATE APPLICATION</div>
          {hardware.reviewDemoEnabled && <div className="review-demo-badge" role="status"><i /> REVIEW BUILD <b>DEMO MODE</b><small>NO LIVE QPU</small></div>}
          <p className="hero-transition">{hardware.reviewDemoEnabled ? <>Review data, not live measurement.<br /><em>Demonstrate the complete vault flow.</em></> : <>You saw randomness measured.<br /><em>Now, let’s use that randomness.</em></>}</p>
          <h1>QUANTUM<br /><span>VAULT</span><i>.</i></h1>
          <p className="hero-subtitle">{hardware.reviewDemoEnabled ? <>A deterministic review fixture. Standard encryption does the rest.</> : <>Your secrets. Locked with randomness<br className="desktop-break" /> from quantum measurement.</>}</p>
          <div className="hero-actions">
            {savedVault ? (
              <button className="button button-dark hero-cta" type="button" onClick={onOpen}>OPEN YOUR VAULT <Icon name="arrow-right" size={17} /></button>
            ) : (
              <button className="button button-dark hero-cta" type="button" onClick={onCreate}>CREATE YOUR VAULT <Icon name="arrow-right" size={17} /></button>
            )}
            <span className="hero-action-note"><Icon name="lock" size={13} /> LOCAL-FIRST · NO ACCOUNT</span>
          </div>
          <div className="hero-microcopy">{hardware.reviewDemoEnabled ? <><span>DETERMINISTIC DEMO BITS</span><span className="micro-divider" /><span>STANDARD AES-256-GCM ENCRYPTION</span></> : <><span>QUANTUM-GENERATED RANDOMNESS</span><span className="micro-divider" /><span>STANDARD AES-256-GCM ENCRYPTION</span></>}</div>
        </div>

        <div className="hero-object-zone">
          <div className="hero-object-kicker"><span>01</span> PHYSICAL SECURITY, REIMAGINED</div>
          <div className="hero-vault-glow" />
          <div className="hero-halo hero-halo-a" /><div className="hero-halo hero-halo-b" />
          <VaultScene open={false} theme={theme} className="hero-vault-scene" interactive scrollMotion />
          <div className="hero-hud hud-entropy">
            <span className="hud-icon"><Icon name="key" size={15} /></span>
            <div><span className="hud-label">{hardware.reviewDemoEnabled ? 'DEMO KEY MATERIAL' : 'KEY MATERIAL'}</span><strong>256 <small>BITS</small></strong><span className="hud-caption">{hardware.reviewDemoEnabled ? 'deterministic fixture' : 'on measurement'}</span></div>
          </div>
          <div className={`hero-hud hud-source ${hardware.reviewDemoEnabled || hardware.available ? 'hud-connected' : ''}`}>
            <span className={`hud-led ${hardware.reviewDemoEnabled || hardware.available ? 'led-green' : ''}`} />
            <div><span className="hud-label">{hardware.reviewDemoEnabled ? 'SOURCE' : 'QUANTUM SOURCE'}</span><strong>{hardware.reviewDemoEnabled ? 'REVIEW DEMO' : hardware.available ? hardware.label.replace(' — real QPU hardware', '') : hardware.connected ? 'NO LIVE IQM QPU' : 'BACKEND OFFLINE'}</strong><span className="hud-caption">{hardware.reviewDemoEnabled ? 'deterministic fixture · no live QPU' : hardware.available ? `live discovery · ${hardware.backend || 'IQM QPU'}` : 'no quantum key will be created'}</span></div>
          </div>
          <div className="vault-status-engraving"><span><Icon name="lock" size={12} /> {savedVault ? 'SEALED ON THIS DEVICE' : 'AWAITING FIRST KEY'}</span><span className="engraving-line" /><span>QV / 001</span></div>
          <div className="hero-coordinate">INSTRUMENT SERIES / 01&nbsp;&nbsp; · &nbsp;&nbsp; LOCAL BY DESIGN</div>
          <div className="hero-object-shadow" />
        </div>

        <a className="scroll-cue" href="#method"><span className="scroll-line" /> SCROLL TO SEE THE METHOD</a>
        <div className={`hero-source-state ${hardware.reviewDemoEnabled ? 'source-demo' : hardware.available ? 'source-online' : ''}`}><i /> {hardware.reviewDemoEnabled ? 'REVIEW DEMO MODE · NO LIVE QPU' : hardware.available ? `LIVE IQM HARDWARE · ${hardware.backend || 'QPU VERIFIED'}` : hardware.connected ? 'NO OPERATIONAL IQM QPU' : 'HARDWARE BACKEND OFFLINE'}</div>
      </section>

      <section className="method-section" id="method">
        <div className="section-heading reveal-item">
          <p className="eyebrow"><span className="section-index">01</span> A DIFFERENT KIND OF KEY</p>
          <h2>{hardware.reviewDemoEnabled ? <>A review flow.<br /><em>Not a live measurement.</em></> : <>Not predicted.<br /><em>Measured.</em></>}</h2>
          <p className="section-lede">{hardware.reviewDemoEnabled ? 'A deterministic 320-bit fixture follows the same visual steps. No provider request is made.' : 'A fixed quantum circuit is sent to a real processor. The returned measurements—not a simulation—become key material.'}</p>
        </div>
        <div className="method-artifact reveal-item">
          <div className="artifact-topline"><span>MEASUREMENT / SCHEMATIC</span><span>01 — 03</span></div>
          <div className="method-circuit" aria-label="Schematic circuit: initial state, Hadamard gate, measurement">
            <div className="circuit-source-node"><span>|0⟩</span><small>INITIAL STATE</small></div>
            <div className="method-wire"><i className="wire-pulse" /></div>
            <div className="method-gate">H</div>
            <div className="method-wire"><i className="wire-pulse wire-pulse-late" /></div>
            <div className="method-measure"><span>M</span><i /></div>
            <div className="method-wire" />
            <div className="measurement-outcome"><span>0</span><b>OR</b><span>1</span></div>
          </div>
          <div className="artifact-bottomline"><span>HADAMARD</span><span>{hardware.reviewDemoEnabled ? 'DEMO FLOW' : 'PHYSICAL MEASUREMENT'}</span><span>{hardware.reviewDemoEnabled ? 'DETERMINISTIC FIXTURE' : 'OUTCOME NOT KNOWN IN ADVANCE'}</span></div>
        </div>
        <div className="method-caption reveal-item"><span className="caption-rule" /><p>{hardware.reviewDemoEnabled ? 'Review mode shows deterministic demonstration bits only. They are not returned by a provider or generated by a quantum processor.' : 'A visual explanation only. The vault shows a live measurement stream only after a provider returns real results.'}</p></div>
      </section>

      <section className="security-section" id="security">
        <div className="security-section-top reveal-item">
          <p className="eyebrow"><span className="section-index">02</span> RANDOMNESS, THEN CRYPTOGRAPHY</p>
          <h2>{hardware.reviewDemoEnabled ? <>Demo bits are the input.<br /><em>Encryption is standard.</em></> : <>Quantum is the source.<br /><em>Encryption is standard.</em></>}</h2>
          <p className="section-lede">{hardware.reviewDemoEnabled ? 'The review fixture supplies predictable demo key material. Well-established cryptography still encrypts the vault.' : 'Quantum measurement supplies fresh randomness. Well-established cryptography does the protecting.'}</p>
        </div>
        <div className="security-flow reveal-item">
          <FlowNode number="01" icon="cpu" title={hardware.reviewDemoEnabled ? 'REVIEW DEMO' : 'QUANTUM'} line={hardware.reviewDemoEnabled ? 'deterministic bits' : 'measurement'} />
          <span className="flow-connector"><i /></span>
          <FlowNode number="02" icon="disc" title={hardware.reviewDemoEnabled ? 'DEMO BITS' : 'RANDOM BITS'} line={hardware.reviewDemoEnabled ? 'deterministic fixture' : '256-bit material'} />
          <span className="flow-connector"><i /></span>
          <FlowNode number="03" icon="lock" title="AES-256-GCM" line="authenticated encryption" />
          <span className="flow-connector"><i /></span>
          <FlowNode number="04" icon="shield" title="LOCAL VAULT" line="encrypted at rest" />
        </div>
        <div className="security-clarifier reveal-item"><span className="clarifier-mark"><Icon name="shield" size={16} /></span><p>{hardware.reviewDemoEnabled ? <><strong>REVIEW DEMO · NO LIVE QPU.</strong> The deterministic fixture supplies demo key material; AES-256-GCM still encrypts the vault. Your password wraps the key using PBKDF2-SHA-256.</> : <><strong>No “quantum encryption” claims.</strong> Quantum hardware supplies randomness; AES-256-GCM encrypts the vault. Your password wraps the key using PBKDF2-SHA-256.</>}</p><span className="clarifier-stamp">PRECISE BY DESIGN</span></div>
      </section>

      <section className="closing-section">
        <div className="closing-seal"><BrandMark size={44} /></div>
        <p className="eyebrow">{hardware.reviewDemoEnabled ? 'REVIEW BUILD · END-TO-END DEMONSTRATION' : 'THE NEXT STEP AFTER MEASUREMENT'}</p>
        <h2>Keep what matters<br /><em>under lock.</em></h2>
        <p className="closing-copy">{hardware.reviewDemoEnabled ? 'A deterministic review fixture. Real AES-GCM. One locally stored vault. No raw key displayed.' : 'A separate application. One locally stored vault. No raw key displayed.'}</p>
        {savedVault ? (
          <button className="button button-dark hero-cta" type="button" onClick={onOpen}>RETURN TO YOUR VAULT <Icon name="arrow-right" size={16} /></button>
        ) : (
          <button className="button button-dark hero-cta" type="button" onClick={onCreate}>CREATE YOUR VAULT <Icon name="arrow-right" size={16} /></button>
        )}
      </section>

      <footer className="landing-footer"><a className="footer-brand" href="#top"><BrandMark size={23} /><span>QUANTUM <b>VAULT</b></span></a><span className="footer-note">Prototype demonstration — not intended for production credential storage.</span><span className="footer-edition">SEPARATE APPLICATION · 2026</span></footer>
    </main>
  )
}

function FlowNode({ number, icon, title, line }: { number: string; icon: 'cpu' | 'disc' | 'lock' | 'shield'; title: string; line: string }) {
  return <div className="flow-node"><span className="flow-number">{number}</span><span className="flow-icon"><Icon name={icon} size={18} /></span><strong>{title}</strong><small>{line}</small></div>
}

