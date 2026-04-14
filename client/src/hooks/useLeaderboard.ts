import { useState, useRef, useEffect } from 'react';
import type { DriverPosition, Frame } from '../types/api.types';

/** Controls whether gaps are shown relative to the car directly ahead or to the race leader. */
type GapMode = 'interval' | 'leader';

/**
 * A `DriverPosition` augmented with the driver's code and pre-computed gap values
 * for both display modes. Gaps are in seconds, derived from track distance.
 *
 * @property {string} code - Three-letter driver code (e.g. `"VER"`).
 * @property {number} gapToLeader - Time gap in seconds to the race leader.
 * @property {number} intervalGap - Time gap in seconds to the car immediately ahead.
 */
export interface DriverWithGap extends DriverPosition {
  code: string;
  gapToLeader: number;
  intervalGap: number;
}

/**
 * Assumed average reference speed in m/s used to convert track-distance differences
 * into approximate time gaps. 55.56 m/s ≈ 200 km/h, a rough mid-session average.
 */
const REFERENCE_SPEED_MS = 55.56;

/**
 * Derives a sorted leaderboard with time gaps from a raw telemetry frame.
 * Handles three distinct race phases transparently:
 * - **Live racing** — drivers sorted by cumulative track distance (lap + relative distance).
 * - **Post-finish** — finished drivers locked to their official positions; still-racing
 *   drivers continue to sort by distance below them.
 * - **Race over** — all drivers sorted entirely by official positions.
 *
 * Gaps for finished drivers are frozen at the moment they cross the line and held
 * constant thereafter, so the leaderboard doesn't show nonsensical values once a
 * driver stops accumulating distance.
 *
 * Scrubbing the playback backwards more than 10 seconds clears frozen gaps so they
 * recalculate correctly from the earlier point in time.
 *
 * @param {Frame | null} currentFrame - The telemetry frame to derive the leaderboard from.
 *   Returns an inert default when null.
 * @param {Record<string, number>} officialPositions - Map of driver code to official
 *   finishing position; used to lock order once results are confirmed.
 *
 * @returns {{
 *   sortedDrivers: DriverWithGap[],
 *   gapMode: GapMode,
 *   setGapMode: (mode: GapMode) => void,
 *   getDisplayGap: (driver: DriverWithGap) => number,
 * }} The sorted driver array, the active gap mode, a setter, and a gap accessor.
 */
export function useLeaderboard(
  currentFrame: Frame | null,
  officialPositions: Record<string, number>,
) {
  const [gapMode, setGapMode] = useState<GapMode>('interval');
  const finishGapsRef    = useRef<Record<string, { toLeader: number; interval: number }>>({});
  const lastFrameTimeRef = useRef<number>(0);

  /**
   * Detects backward scrubbing (more than 10 s jump back) and clears frozen finish
   * gaps so they are recalculated from the new playback position rather than
   * showing stale values from a later point in the race.
   */
  useEffect(() => {
    if (currentFrame && currentFrame.t < lastFrameTimeRef.current - 10) {
      finishGapsRef.current = {};
    }
    lastFrameTimeRef.current = currentFrame?.t ?? 0;
  }, [currentFrame]);

  /** Return a stable inert value when no frame is available (e.g. before data loads). */
  if (!currentFrame) return { sortedDrivers: [], gapMode, setGapMode, getDisplayGap: () => 0 };

  const hasOfficialPositions = Object.keys(officialPositions).length > 0;

  /** Flatten the frame's driver map into an array, injecting the driver code and zero-initialised gaps. */
  const driversArray: DriverWithGap[] = Object.entries(currentFrame.drivers).map(
    ([code, pos]) => ({ code, ...pos, gapToLeader: 0, intervalGap: 0 })
  );

  /** True when official results are available and at least one driver has finished. */
  const raceOver = hasOfficialPositions && driversArray.some(d => d.finished);

  /**
   * Sort priority:
   * 1. Retired drivers always sink to the bottom.
   * 2. When the race is fully over, sort entirely by official position.
   * 3. Finished drivers (chequered flag taken) rank above still-racing drivers,
   *    using official positions to break ties among multiple finishers.
   * 4. Still-racing drivers sort by cumulative track progress (laps + rel_dist).
   */
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

  /** Absolute track distance of the leading car, used as the reference for all gap calculations. */
  const leaderDist = driversArray.find(d => !d.is_out)?.dist ?? 0;

  /**
   * Compute gaps for each driver and freeze them the first time a driver is seen as finished.
   * Gap values are converted from metres to seconds using `REFERENCE_SPEED_MS`.
   */
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

  /**
   * Returns the gap value to display for a given driver, respecting the active
   * `gapMode` and using the frozen finish-line gap for drivers who have finished.
   *
   * @param {DriverWithGap} driver - The driver whose gap should be retrieved.
   * @returns {number} Gap in seconds to display in the leaderboard.
   */
  const getDisplayGap = (driver: DriverWithGap): number => {
    const frozen = finishGapsRef.current[driver.code];
    if (driver.finished && frozen) {
      return gapMode === 'interval' ? frozen.interval : frozen.toLeader;
    }
    return gapMode === 'interval' ? driver.intervalGap : driver.gapToLeader;
  };

  return { sortedDrivers: driversArray, gapMode, setGapMode, getDisplayGap };
}
