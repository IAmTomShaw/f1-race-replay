// ── index.tsx ────────────────────────────────────────────────────────────────
import { useState } from 'react';
import type { WeatherData } from '../../../types/api.types';
import WeatherWidget from '../Weather';
import './index.css';

interface NavbarProps {
  onHome: () => void;
  onToggleComparison?: () => void;
  isComparisonMode?: boolean;
  weather?: WeatherData | null;
}

export default function Navbar({ onHome, onToggleComparison, isComparisonMode, weather }: NavbarProps) {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <nav className="navbar">
        <div className="navbar-top">
          <button className="nav-btn nav-home" onClick={onHome} title="Home">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
            </svg>
          </button>

          
          <button
            className={`nav-btn nav-info${isComparisonMode ? ' nav-btn--active' : ''}`}
            onClick={onToggleComparison}
            title="Driver Summary"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
            </svg>
          </button>

          <button className="nav-btn nav-info" onClick={() => setModalOpen(true)} title="About">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/>
            </svg>
          </button>
        </div>

        <div className="navbar-bottom">
          <WeatherWidget weather={weather} />
        </div>
      </nav>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setModalOpen(false)}>✕</button>
            <h2 className="modal-title">About This Project</h2>

            <section className="modal-section">
              <h3 className="modal-section-title">Credits</h3>
              <p className="modal-text">
                This project is based on{' '}
                <a className="modal-link" href="https://github.com/IAmTomShaw/f1-race-replay"
                  target="_blank" rel="noopener noreferrer">Race Replay</a>{' '}
                by <strong>IAmTomShaw</strong>. Building on the foundational work of Tom Shaw,
                the original repository provided the core logic for parsing and rendering F1
                telemetry data. It has since been significantly refactored and extended with a
                focus on interactivity and visual polish.
              </p>
            </section>

            <section className="modal-section">
              <h3 className="modal-section-title">Follow The Development</h3>
              <div className="modal-links">
                <a className="modal-follow-btn"
                  href="https://github.com/meredithscott131/f1-race-replay"
                  target="_blank" rel="noopener noreferrer">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
                  </svg>
                  GitHub
                </a>
              </div>
            </section>
          </div>
        </div>
      )}
    </>
  );
}
