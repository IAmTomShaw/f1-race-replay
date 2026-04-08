import type { Frame } from '../../../types/api.types';
import { useLeaderboard } from '../../../hooks/useLeaderboard';
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

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

export default function Leaderboard({
  currentFrame, driverColors, totalLaps, driverTeams,
  officialPositions = {}, focusedDrivers, onToggleDriver,
}: LeaderboardProps) {
  const { sortedDrivers, gapMode, setGapMode, getDisplayGap } =
    useLeaderboard(currentFrame, officialPositions);

  if (!currentFrame) return null;

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
        {sortedDrivers.map((driver, idx) => {
          const rowPos       = idx + 1;
          const tyreCompound = TYRE_COMPOUNDS[Math.floor(driver.tyre)] || TYRE_COMPOUNDS[0];
          const teamName     = driverTeams?.[driver.code] || '';
          const logoFilename = getTeamLogo(teamName) ?? '';
          const gap          = getDisplayGap(driver);
          const isFocused    = focusedDrivers.has(driver.code);
          const isDimmed     = anyFocused && !isFocused;
          const color        = driverColors[driver.code];
          const accentColor  = color ? `rgb(${color[0]},${color[1]},${color[2]})` : 'transparent';

          return (
            <div
              key={driver.code}
              className={[
                'lb-entry',
                driver.is_out ? 'lb-entry--out'     : '',
                rowPos === 1  ? 'lb-entry--leader'  : '',
                isFocused     ? 'lb-entry--focused' : '',
                isDimmed      ? 'lb-entry--dimmed'  : '',
              ].filter(Boolean).join(' ')}
              onClick={() => onToggleDriver(driver.code)}
              title={isFocused ? `Hide ${driver.code}` : `Focus ${driver.code}`}
            >
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
