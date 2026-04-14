import type { TrackData } from '../../../types/track.types';
import type { Frame } from '../../../types/api.types';
import { useAnimatedTrackCanvas } from '../../../hooks/useAnimatedTrackCanvas';
import './index.css';

/**
 * Props for the AnimatedTrackCanvas component.
 *
 * @property {TrackData | null} [trackData] - Static track geometry (boundaries, DRS zones, bounds).
 * @property {Frame[]} [frames] - Full ordered array of telemetry frames for the session.
 * @property {Record<string, [number, number, number]>} [driverColors] - Map of driver code to RGB color tuple.
 * @property {number} currentFrame - Index into `frames` representing the current playback position.
 * @property {Frame | null} [interpolatedFrame] - Smoothly interpolated frame for sub-frame rendering; takes priority over `frames[currentFrame]`.
 * @property {string | null} [leaderCode] - Driver code of the current race leader; a gold star is drawn above their dot.
 * @property {Set<string>} [focusedDrivers] - When non-empty, all drivers outside this set are dimmed to ghost dots.
 * @property {boolean} [comparisonMode] - When true, live driver dots are hidden and historical comparison dots are shown instead.
 * @property {{ year: number; x: number; y: number; is_retired: boolean }[]} [comparisonPositions] - Per-year historical positions for the selected comparison driver.
 * @property {[number, number, number]} [comparisonDriverColor] - RGB color for the comparison driver's dots; falls back to white.
 */
interface AnimatedTrackCanvasProps {
  trackData?: TrackData | null;
  frames?: Frame[];
  driverColors?: Record<string, [number, number, number]>;
  currentFrame: number;
  interpolatedFrame?: Frame | null;
  leaderCode?: string | null;
  focusedDrivers?: Set<string>;
  comparisonMode?: boolean;
  comparisonPositions?: { year: number; x: number; y: number; is_retired: boolean }[];
  comparisonDriverColor?: [number, number, number];
}

/**
 * AnimatedTrackCanvas renders the live F1 circuit map on an HTML5 canvas.
 *
 * All rendering and interaction logic (scaling, drawing, zoom, pan, follow) lives
 * in `useAnimatedTrackCanvas`. This component is a pure render shell that wires
 * the hook's refs and handlers to the DOM.
 *
 * @param {AnimatedTrackCanvasProps} props - Component props.
 * @returns {JSX.Element} A container `<div>` holding the `<canvas>` and a camera-reset button.
 */
export default function AnimatedTrackCanvas(props: AnimatedTrackCanvasProps) {
  const { canvasRef, containerRef, handleResetCamera } = useAnimatedTrackCanvas(props);

  return (
    <div ref={containerRef} className="animated-track-canvas-container">
      <canvas ref={canvasRef} className="animated-track-canvas" />
      {!props.trackData && (
        <div className="track-loading-placeholder">
          <p>Loading track data...</p>
        </div>
      )}
      <button className="reset-camera-btn" onClick={handleResetCamera} title="Reset camera">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 8V3h5M21 8V3h-5M3 16v5h5M21 16v5h-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
        </svg>
      </button>
    </div>
  );
}
