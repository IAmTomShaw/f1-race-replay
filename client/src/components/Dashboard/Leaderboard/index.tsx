import { useState, useRef, useEffect } from 'react';
import type { Frame, DriverPosition } from '../../../types/api.types';
import { getTeamLogo } from '../../../utils/teamLogos';
import { teamLogoUrl } from '../../../lib/assets';
import F1Header from './F1Header';
import '../../../styles/variables.css';
import './index.css';

interface LeaderboardProps {
  currentFrame: Frame | null;
  driverColors: Record<string, [number, number, number]>;
  driverTeams?: Record<string, string>;
  totalLaps?: number;
  officialPositions?: Record<string, number>;
  focusedDrivers: Set<string>;
  onToggleDriver: (code: string) => void;
}

const TYRE_COMPOUNDS: Record<number, { letter: string; bg: string }> = {
  0: { letter: 'S', bg: '#FF0000' },
  1: { letter: 'M', bg: '#FFFF00' },
  2: { letter: 'H', bg: '#bbbbbb' },
  3: { letter: 'I', bg: '#00FF00' },
  4: { letter: 'W', bg: '#0066FF' },
};

type GapMode = 'interval' | 'leader';

interface DriverWithGap extends DriverPosition {
  code: string;
  gapToLeader: number;
  intervalGap: number;
}

export default function Leaderboard({
  currentFrame, driverColors, totalLaps, driverTeams,
  officialPositions = {}, focusedDrivers, onToggleDriver,
}: LeaderboardProps) {
  const [gapMode, setGapMode] = useState<GapMode>('interval');
  const finishGapsRef    = useRef<Record<string, { toLeader: number; interval: number }>>({});
  const lastFrameTimeRef = useRef<number>(0);

  useEffect(() => {
    if (currentFrame && currentFrame.t < lastFrameTimeRef.current - 10) {
      finishGapsRef.current = {};
    }
    lastFrameTimeRef.current = currentFrame?.t ?? 0;
  }, [currentFrame]);

  if (!currentFrame) return null;

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const driversArray: DriverWithGap[] = Object.entries(currentFrame.drivers).map(([code, pos]) => ({
    code, ...pos, gapToLeader: 0, intervalGap: 0,
  }));

  const hasOfficialPositions = Object.keys(officialPositions).length > 0;
  const raceOver = hasOfficialPositions && driversArray.some(d => d.finished);

  driversArray.sort((a, b) => {
    // Retired drivers always sink to the bottom
    if (a.is_out && !b.is_out) return 1;
    if (!a.is_out && b.is_out) return -1;
    if (a.is_out && b.is_out) return 0;

    // Once the winner has crossed the line, use official positions for everyone
    if (raceOver) {
      const posA = officialPositions[a.code] ?? 99;
      const posB = officialPositions[b.code] ?? 99;
      return posA - posB;
    }

    // Mid-race: finished lead-lap drivers above lapped cars still racing
    if (a.finished && b.finished) {
      const posA = officialPositions[a.code] ?? a.position;
      const posB = officialPositions[b.code] ?? b.position;
      return posA - posB;
    }
    if (a.finished && !b.finished) return -1;
    if (!a.finished && b.finished) return 1;

    // Live race ordering by progress
    const progressA = (a.lap - 1) + a.rel_dist;
    const progressB = (b.lap - 1) + b.rel_dist;
    return progressB - progressA;
  });

  const REFERENCE_SPEED_MS = 55.56;
  const leaderDist = driversArray.find(d => !d.is_out)?.dist ?? 0;

  driversArray.forEach((driver, idx) => {
    if (idx === 0) {
      driver.gapToLeader = 0;
      driver.intervalGap = 0;
    } else {
      driver.gapToLeader = Math.abs(leaderDist - driver.dist) / REFERENCE_SPEED_MS;
      driver.intervalGap = Math.abs(driversArray[idx - 1].dist - driver.dist) / REFERENCE_SPEED_MS;
    }
    if (driver.finished && !finishGapsRef.current[driver.code]) {
      finishGapsRef.current[driver.code] = {
        toLeader: driver.gapToLeader,
        interval: driver.intervalGap,
      };
    }
  });

  const anyFocused = focusedDrivers.size > 0;

  return (
    <div className="leaderboard">
      <F1Header />
      <div className="leaderboard-header">
        <div className="header-info-item">
          <span className="header-label">LAP</span>
          <span className="header-value-bold">{currentFrame.lap}</span>
          <span className="header-value">{totalLaps ? `/${totalLaps}` : ''}</span>
        </div>
        <div className="header-right">
          <span className="header-time">{formatTime(currentFrame.t)}</span>
        </div>
      </div>

      <div className="leaderboard-entries">
        {driversArray.map((driver, idx) => {
          const rowPos       = idx + 1;
          const tyreCompound = TYRE_COMPOUNDS[Math.floor(driver.tyre)] || TYRE_COMPOUNDS[0];
          const teamName     = driverTeams?.[driver.code] || '';
          const logoFilename = getTeamLogo(teamName) ?? '';
          const frozenGap    = finishGapsRef.current[driver.code];
          const gap = driver.finished && frozenGap
            ? (gapMode === 'interval' ? frozenGap.interval : frozenGap.toLeader)
            : (gapMode === 'interval' ? driver.intervalGap : driver.gapToLeader);

          const isFocused  = focusedDrivers.has(driver.code);
          const isDimmed   = anyFocused && !isFocused;
          const color      = driverColors[driver.code];
          const accentColor = color ? `rgb(${color[0]},${color[1]},${color[2]})` : 'transparent';

          return (
            <div
              key={driver.code}
              className={[
                'lb-entry',
                driver.is_out ? 'lb-entry--out'    : '',
                rowPos === 1  ? 'lb-entry--leader' : '',
                isFocused     ? 'lb-entry--focused' : '',
                isDimmed      ? 'lb-entry--dimmed'  : '',
              ].filter(Boolean).join(' ')}
              onClick={() => onToggleDriver(driver.code)}
              title={isFocused ? `Hide ${driver.code}` : `Focus ${driver.code}`}
            >
              {/* Focus accent bar */}
              <div
                className="lb-focus-bar"
                style={{ backgroundColor: isFocused ? accentColor : 'transparent' }}
              />

              <div className="lb-position">{driver.is_out ? '' : rowPos}</div>
              <div className="lb-driver">
                <img
                  src={teamLogoUrl(logoFilename)}
                  alt={teamName}
                  className="lb-team-logo"
                  onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
                />
                <span className="lb-code">{driver.code}</span>
              </div>
              <div className="lb-gap">
                {driver.is_out ? (
                  <span className="gap-out">OUT</span>
                ) : rowPos === 1 ? (
                  <span className="gap-leader">-</span>
                ) : (
                  <span className="gap-value">+{gap.toFixed(1)}</span>
                )}
              </div>
              <div className="lb-tyre" style={{ color: driver.is_out ? 'transparent' : tyreCompound.bg }}>
                {driver.is_out ? '' : tyreCompound.letter}
              </div>
            </div>
          );
        })}
      </div>

      <div className="leaderboard-footer">
        {anyFocused && (
          <button
            className="focus-reset-btn"
            onClick={() => focusedDrivers.forEach(c => onToggleDriver(c))}
          >
            SHOW ALL
          </button>
        )}
        <div className="gap-toggle">
          <button
            className={`gap-toggle-btn${gapMode === 'interval' ? ' active' : ''}`}
            onClick={() => setGapMode('interval')}
          >INT</button>
          <button
            className={`gap-toggle-btn${gapMode === 'leader' ? ' active' : ''}`}
            onClick={() => setGapMode('leader')}
          >LDR</button>
        </div>
      </div>
    </div>
  );
}
