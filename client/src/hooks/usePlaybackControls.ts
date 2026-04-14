import { useState } from 'react';

/**
 * The discrete set of supported playback speed multipliers, in ascending order.
 * Speed changes step through this array one index at a time in both directions.
 */
const PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];

/**
 * Derives all UI-level control state and interaction handlers for the playback
 * control bar. Acts as a thin adapter between raw playback callbacks (seek, speed)
 * and the specific button/input interactions the UI needs.
 *
 * @param {number} currentFrame - The current playback frame index.
 * @param {number} totalFrames - Total number of frames in the replay.
 * @param {number} totalLaps - Total laps in the race; used to bound lap navigation.
 * @param {number[]} lapFrameIndices - Frame index at which each lap begins; used to
 *   derive `currentLap` and to gate prev/next-lap buttons.
 * @param {number} playbackSpeed - Current speed multiplier (must be a value in `PLAYBACK_SPEEDS`).
 * @param {(speed: number) => void} onSpeedChange - Callback to update the playback speed.
 * @param {(frame: number) => void} onSeek - Callback to jump to a specific frame index.
 * @param {(lap: number) => void} onSeekToLap - Callback to jump to the start of a specific lap.
 *
 * @returns {{
 *   currentLap: number | null,
 *   progress: number,
 *   lapInputValue: string,
 *   setLapInputValue: (value: string) => void,
 *   commitLap: (raw: string) => void,
 *   handleSpeedIncrease: () => void,
 *   handleSpeedDecrease: () => void,
 *   handleProgressClick: (e: React.MouseEvent<HTMLDivElement>) => void,
 *   handlePrevLap: () => void,
 *   handleNextLap: () => void,
 *   canDecreaseLap: boolean,
 *   canIncreaseLap: boolean,
 *   canDecreaseSpeed: boolean,
 *   canIncreaseSpeed: boolean,
 * }}
 */
export function usePlaybackControls(
  currentFrame: number,
  totalFrames: number,
  totalLaps: number,
  lapFrameIndices: number[],
  playbackSpeed: number,
  onSpeedChange: (speed: number) => void,
  onSeek: (frame: number) => void,
  onSeekToLap: (lap: number) => void,
) {
  const [lapInputValue, setLapInputValue] = useState('');
  const currentLap = lapFrameIndices.length > 0
    ? getCurrentLap(currentFrame, lapFrameIndices)
    : null;
  const progress = totalFrames > 0 ? (currentFrame / totalFrames) * 100 : 0;

  /**
   * Steps the speed up by one entry in `PLAYBACK_SPEEDS`.
   * No-ops when already at the maximum speed.
   */
  const handleSpeedIncrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i < PLAYBACK_SPEEDS.length - 1) onSpeedChange(PLAYBACK_SPEEDS[i + 1]);
  };

  /**
   * Steps the speed down by one entry in `PLAYBACK_SPEEDS`.
   * No-ops when already at the minimum speed.
   */
  const handleSpeedDecrease = () => {
    const i = PLAYBACK_SPEEDS.indexOf(playbackSpeed);
    if (i > 0) onSpeedChange(PLAYBACK_SPEEDS[i - 1]);
  };

  /**
   * Seeks to the frame that corresponds to the click position along the progress bar.
   * The target frame is derived from the click's horizontal percentage within the element.
   *
   * @param {React.MouseEvent<HTMLDivElement>} e - The click event on the progress bar container.
   */
  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect    = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    onSeek(Math.floor(percent * totalFrames));
  };

  /**
   * Parses a raw string from the lap input and seeks to that lap if the value
   * is a valid integer. Always clears `lapInputValue` after attempting the commit,
   * even if the value was invalid.
   *
   * @param {string} raw - The raw string value from the input element.
   */
  const commitLap = (raw: string) => {
    const n = parseInt(raw, 10);
    if (!isNaN(n)) onSeekToLap(n);
    setLapInputValue('');
  };

  /** Seeks to the previous lap. No-ops when `currentLap` is null or already at lap 1. */
  const handlePrevLap = () => { if (currentLap) onSeekToLap(currentLap - 1); };
  /** Seeks to the next lap. No-ops when `currentLap` is null or already at the final lap. */
  const handleNextLap = () => { if (currentLap) onSeekToLap(currentLap + 1); };

  const canDecreaseLap  = currentLap !== null && currentLap > 1;
  const canIncreaseLap  = currentLap !== null && currentLap < totalLaps;
  const canDecreaseSpeed = playbackSpeed === PLAYBACK_SPEEDS[0];
  const canIncreaseSpeed = playbackSpeed === PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.length - 1];

  return {
    currentLap,
    progress,
    lapInputValue,
    setLapInputValue,
    commitLap,
    handleSpeedIncrease,
    handleSpeedDecrease,
    handleProgressClick,
    handlePrevLap,
    handleNextLap,
    canDecreaseLap,
    canIncreaseLap,
    canDecreaseSpeed,
    canIncreaseSpeed,
  };
}

/**
 * Determines the current 1-based lap number for a given frame index by scanning
 * the lap boundary index array from left to right. The lap increments each time
 * `frameIdx` is at or past a lap boundary; the loop breaks early on the first
 * boundary the frame hasn't reached yet.
 *
 * @param {number} frameIdx - The frame index to evaluate.
 * @param {number[]} lapFrameIndices - Ordered array of frame indices at which each lap starts.
 * @returns {number} The 1-based lap number containing `frameIdx`.
 */
function getCurrentLap(frameIdx: number, lapFrameIndices: number[]): number {
  let lap = 1;
  for (let i = 0; i < lapFrameIndices.length; i++) {
    if (frameIdx >= lapFrameIndices[i]) lap = i + 1;
    else break;
  }
  return lap;
}
