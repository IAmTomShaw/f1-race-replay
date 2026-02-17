import type { Frame, DriverPosition } from '../../types/api.types';
import F1Header from './F1Header';
import './index.css';

interface LeaderboardProps {
  currentFrame: Frame | null;
  driverColors: Record<string, [number, number, number]>;
  totalLaps?: number;
}

// Tyre compound mapping
const TYRE_COMPOUNDS: Record<number, { letter: string; bg: string }> = {
  0: { letter: 'S', bg: '#FF0000' },     // Soft - Red
  1: { letter: 'M', bg: '#FFFF00' },     // Medium - Yellow
  2: { letter: 'H', bg: '#FFFFFF' },     // Hard - White
  3: { letter: 'I', bg: '#00FF00' },     // Intermediate - Green
  4: { letter: 'W', bg: '#0066FF' },     // Wet - Blue
};

interface DriverWithGap extends DriverPosition {
  code: string;
  gapToLeader: number;
  intervalGap: number;
}

export default function Leaderboard({ currentFrame, driverColors, totalLaps }: LeaderboardProps) {
  if (!currentFrame) return null;

  // Format time as MM:SS
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Calculate positions and gaps
  const driversArray: DriverWithGap[] = Object.entries(currentFrame.drivers).map(([code, pos]) => ({
    code,
    ...pos,
    gapToLeader: 0,
    intervalGap: 0,
  }));

  // Sort by position
  driversArray.sort((a, b) => a.position - b.position);

  // Calculate gaps
  const REFERENCE_SPEED_MS = 55.56;
  const leaderDist = driversArray[0]?.dist || 0;

  driversArray.forEach((driver, idx) => {
    if (idx === 0) {
      driver.gapToLeader = 0;
      driver.intervalGap = 0;
    } else {
      const distToLeader = Math.abs(leaderDist - driver.dist);
      driver.gapToLeader = distToLeader / REFERENCE_SPEED_MS;

      const carAhead = driversArray[idx - 1];
      const distToAhead = Math.abs(carAhead.dist - driver.dist);
      driver.intervalGap = distToAhead / REFERENCE_SPEED_MS;
    }
  });

  return (
    <div className="leaderboard">
      <F1Header />
      <div className="leaderboard-header">
        <div className="header-info-item">
          <span className="header-label">LAP</span>
          <span className="header-value">
            {currentFrame.lap}{totalLaps ? `/${totalLaps}` : ''}
          </span>
        </div>
        
        <div className="header-info-item">
          <span className="header-value">{formatTime(currentFrame.t)}</span>
        </div>
      </div>

      <div className="leaderboard-entries">
        {driversArray.map((driver) => {
          const color = driverColors[driver.code] || [255, 255, 255];
          const colorStr = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
          const tyreCompound = TYRE_COMPOUNDS[Math.floor(driver.tyre)] || TYRE_COMPOUNDS[0];

          return (
            <div key={driver.code} className="lb-entry">
              <div className="lb-position">{driver.position}</div>
              
              <div className="lb-driver">
                <div 
                  className="lb-color-stripe" 
                  style={{ backgroundColor: colorStr }}
                />
                <span className="lb-code">{driver.code}</span>
              </div>
              
              <div className="lb-gap">
                {driver.position === 1 ? (
                  <span className="gap-leader">INTERVAL</span>
                ) : (
                  <span className="gap-value">+{driver.intervalGap.toFixed(1)}</span>
                )}
              </div>

              <div 
                className="lb-tyre"
                style={{ color: tyreCompound.bg }}
              >
                {tyreCompound.letter}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
