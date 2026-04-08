import { useState, useRef, useEffect } from 'react';
import type { DriverPosition, Frame } from '../types/api.types';

type GapMode = 'interval' | 'leader';

export interface DriverWithGap extends DriverPosition {
  code: string;
  gapToLeader: number;
  intervalGap: number;
}

const REFERENCE_SPEED_MS = 55.56;

export function useLeaderboard(
  currentFrame: Frame | null,
  officialPositions: Record<string, number>,
) {
  const [gapMode, setGapMode]    = useState<GapMode>('interval');
  const finishGapsRef            = useRef<Record<string, { toLeader: number; interval: number }>>({});
  const lastFrameTimeRef         = useRef<number>(0);

  // Reset frozen gaps on scrub backwards
  useEffect(() => {
    if (currentFrame && currentFrame.t < lastFrameTimeRef.current - 10) {
      finishGapsRef.current = {};
    }
    lastFrameTimeRef.current = currentFrame?.t ?? 0;
  }, [currentFrame]);

  if (!currentFrame) return { sortedDrivers: [], gapMode, setGapMode, getDisplayGap: () => 0 };

  const hasOfficialPositions = Object.keys(officialPositions).length > 0;

  const driversArray: DriverWithGap[] = Object.entries(currentFrame.drivers).map(
    ([code, pos]) => ({ code, ...pos, gapToLeader: 0, intervalGap: 0 })
  );

  const raceOver = hasOfficialPositions && driversArray.some(d => d.finished);

  driversArray.sort((a, b) => {
    if (a.is_out && !b.is_out) return 1;
    if (!a.is_out && b.is_out) return -1;
    if (a.is_out && b.is_out)  return 0;

    if (raceOver) {
      return (officialPositions[a.code] ?? 99) - (officialPositions[b.code] ?? 99);
    }

    if (a.finished && b.finished) {
      return (officialPositions[a.code] ?? a.position) - (officialPositions[b.code] ?? b.position);
    }
    if (a.finished && !b.finished) return -1;
    if (!a.finished && b.finished) return 1;

    return ((b.lap - 1) + b.rel_dist) - ((a.lap - 1) + a.rel_dist);
  });

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

  const getDisplayGap = (driver: DriverWithGap): number => {
    const frozen = finishGapsRef.current[driver.code];
    if (driver.finished && frozen) {
      return gapMode === 'interval' ? frozen.interval : frozen.toLeader;
    }
    return gapMode === 'interval' ? driver.intervalGap : driver.gapToLeader;
  };

  return { sortedDrivers: driversArray, gapMode, setGapMode, getDisplayGap };
}
