import { useState } from 'react';
import type { TrackStatus } from '../../../types/api.types';
import './index.css';

interface PlaybackControlsProps {
  isPaused: boolean;
  playbackSpeed: number;
  currentFrame: number;
  totalFrames: number;
  totalLaps?: number;
  lapFrameIndices?: number[];
  trackStatuses?: TrackStatus[];
  totalTime?: number;
  onPlayPause: () => void;
  onSpeedChange: (speed: number) => void;
  onSeek: (frame: number) => void;
  onSeekToLap: (lap: number) => void;
  onRestart: () => void;
  onPrevRace?: () => void;
  onNextRace?: () => void;
  hasPrevRace?: boolean;
  hasNextRace?: boolean;
}

const PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  '2': { color: '#FFD700', label: 'Yellow Flag'          },
  '4': { color: '#F97316', label: 'Safety Car'           },
  '5': { color: '#EF4444', label: 'Red Flag'             },
  '6': { color: '#FB923C', label: 'Virtual Safety Car'   },
  '7': { color: '#FDE68A', label: 'VSC Ending'           },
};

function currentLapFromFrame(frameIdx: number, lapFrameIndices: number[]): number {
  let lap = 1;
  for (let i = 0; i < lapFrameIndices.length; i++) {
    if (frameIdx >= lapFrameIndices[i]) lap = i + 1;
    else break;
  }
  return lap;
}

export default function PlaybackControls({
  isPaused, playbackSpeed, currentFrame, totalFrames,
  totalLaps = 0, lapFrameIndices = [],
  trackStatuses = [], totalTime = 0,
  onPlayPause, onSpeedChange, onSeek, onSeekToLap, onRestart,
  onPrevRace, onNextRace, hasPrevRace = false, hasNextRace = false,
}: PlaybackControlsProps) {
  const [lapInputValue, setLapInputValue] = useState('');

  const handleSpeedIncrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i < PLAYBACK_SPEEDS.length - 1) onSpeedChange(PLAYBACK_SPEEDS[i + 1]);
  };
  const handleSpeedDecrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i > 0) onSpeedChange(PLAYBACK_SPEEDS[i - 1]);
  };

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    onSeek(Math.floor(percent * totalFrames));
  };

  const currentLap = lapFrameIndices.length > 0
    ? currentLapFromFrame(currentFrame, lapFrameIndices)
    : null;

  const commitLap = (raw: string) => {
    const n = parseInt(raw, 10);
    if (!isNaN(n)) onSeekToLap(n);
    setLapInputValue('');
  };

  const progress = totalFrames > 0 ? (currentFrame / totalFrames) * 100 : 0;

  // Only render statuses we have a style for (skip '1' = green/clear)
  const visibleStatuses = totalTime > 0
    ? trackStatuses.filter(s => STATUS_STYLES[s.status])
    : [];

  return (
    <div className="playback-controls">
      {/* ── Progress bar ── */}
      <div className="progress-container" onClick={handleProgressClick}>

        {/* Track status segments */}
        {visibleStatuses.length > 0 && (
          <div className="track-status-strip">
            {visibleStatuses.map((s, i) => {
              const startPct = (s.start_time / totalTime) * 100;
              const endPct   = ((s.end_time ?? totalTime) / totalTime) * 100;
              const style    = STATUS_STYLES[s.status];
              return (
                <div
                  key={i}
                  className="track-status-segment"
                  style={{
                    left:            `${startPct}%`,
                    width:           `${endPct - startPct}%`,
                    backgroundColor: style.color,
                  }}
                  title={style.label}
                />
              );
            })}
          </div>
        )}

        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />

          {totalFrames > 0 && lapFrameIndices.map((frameIdx, i) => {
            const pct = (frameIdx / totalFrames) * 100;
            if (i === 0 || pct > 99.5) return null;
            return (
              <div key={i} className="progress-lap-tick"
                style={{ left: `${pct}%` }} title={`Lap ${i + 1}`} />
            );
          })}

          <div className="progress-handle" style={{ left: `${progress}%` }} />
        </div>

        {currentLap !== null && (
          <div className="progress-lap-label" style={{ left: `${progress}%` }}>
            L{currentLap}
          </div>
        )}
      </div>

      {/* ── Controls row ── */}
      <div className="controls-row">

        <button className="control-btn race-nav-btn-left" onClick={onPrevRace}
          disabled={!hasPrevRace} title="Previous Race">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/>
          </svg>
        </button>

        <div className="controls-container">
          <div className="controls-section">
            <button className="control-btn" onClick={onRestart} title="Restart (R)">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
            </button>
            <button className="control-btn" onClick={() => onSeek(Math.max(0, currentFrame - 250))} title="Rewind (←)">
              <svg width="25" height="25" viewBox="0 0 24 24" fill="currentColor">
                <path d="M11 18V6l-8.5 6 8.5 6zm.5-6 8.5 6V6l-8.5 6z"/>
              </svg>
            </button>
            <button className="control-btn control-btn-primary" onClick={onPlayPause} title="Play/Pause (Space)">
              {isPaused
                ? <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                : <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
              }
            </button>
            <button className="control-btn" onClick={() => onSeek(Math.min(totalFrames - 1, currentFrame + 250))} title="Forward (→)">
              <svg width="25" height="25" viewBox="0 0 24 24" fill="currentColor">
                <path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/>
              </svg>
            </button>
          </div>

          <div className="controls-divider" />

          <div className="controls-section">
            <div className="speed-display">
              <button className="speed-btn" onClick={handleSpeedDecrease}
                disabled={playbackSpeed === PLAYBACK_SPEEDS[0]} title="Decrease Speed (↓)">−</button>
              <span className="speed-value">{playbackSpeed}x</span>
              <button className="speed-btn" onClick={handleSpeedIncrease}
                disabled={playbackSpeed === PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.length - 1]} title="Increase Speed (↑)">+</button>
            </div>
          </div>

          {totalLaps > 0 && (
            <>
              <div className="controls-divider" />
              <div className="controls-section">
                <div className="lap-display">
                  <button className="speed-btn"
                    onClick={() => currentLap && onSeekToLap(currentLap - 1)}
                    disabled={currentLap === null || currentLap <= 1}
                    title="Previous Lap">−</button>
                  <div className="lap-input-wrapper" title="Type a lap number and press Enter">
                    <span className="lap-label">Lap</span>
                    <input
                      className="lap-input"
                      type="number" min={1} max={totalLaps}
                      value={lapInputValue !== '' ? lapInputValue : (currentLap ?? '')}
                      onChange={e => setLapInputValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') commitLap((e.target as HTMLInputElement).value);
                        if (e.key === 'Escape') setLapInputValue('');
                      }}
                      onBlur={e => { if (lapInputValue !== '') commitLap(e.target.value); }}
                    />
                    <span className="lap-total">/ {totalLaps}</span>
                  </div>
                  <button className="speed-btn"
                    onClick={() => currentLap && onSeekToLap(currentLap + 1)}
                    disabled={currentLap === null || currentLap >= totalLaps}
                    title="Next Lap">+</button>
                </div>
              </div>
            </>
          )}
        </div>

        <button className="control-btn race-nav-btn-right" onClick={onNextRace}
          disabled={!hasNextRace} title="Next Race">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zm9-12v12h2V6h-2z"/>
          </svg>
        </button>

      </div>
    </div>
  );
}
