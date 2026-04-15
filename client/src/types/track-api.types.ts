/**
 * A two-dimensional point in the circuit's world coordinate space.
 *
 * @property {number} x - Horizontal world-space coordinate.
 * @property {number} y - Vertical world-space coordinate.
 */
export interface Point {
  x: number;
  y: number;
}

/**
 * The axis-aligned bounding box of the full circuit geometry.
 * Used by `calculateScaling` to determine the centroid and optimal rotation
 * that maximises the circuit's use of the available canvas area.
 *
 * @property {number} minX - Smallest X value across all boundary points.
 * @property {number} maxX - Largest X value across all boundary points.
 * @property {number} minY - Smallest Y value across all boundary points.
 * @property {number} maxY - Largest Y value across all boundary points.
 */
export interface TrackBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/**
 * A DRS activation zone defined as a contiguous slice of the outer boundary
 * point array. Rendered as a green overlay on the track canvas.
 *
 * @property {number} startIndex - Index into `TrackData.outerBoundary` where the DRS zone begins.
 * @property {number} endIndex - Index into `TrackData.outerBoundary` where the DRS zone ends (inclusive).
 */
export interface DRSZoneSegment {
  startIndex: number;
  endIndex: number;
}

/**
 * The fully processed, canvas-ready representation of a circuit.
 * Produced by `buildTrackFromFrames` and consumed directly by `AnimatedTrackCanvas`.
 *
 * @property {Point[]} innerBoundary - Ordered world-space points tracing the inner edge of the circuit.
 * @property {Point[]} outerBoundary - Ordered world-space points tracing the outer edge of the circuit.
 * @property {Point[]} centerLine - Ordered world-space points along the racing line centre.
 * @property {TrackBounds} bounds - Pre-computed axis-aligned bounding box of the full geometry.
 * @property {DRSZoneSegment[]} [drsZones] - Optional DRS zone definitions; absent when not available
 *   for the circuit or session type.
 */
export interface TrackData {
  innerBoundary: Point[];
  outerBoundary: Point[];
  centerLine: Point[];
  bounds: TrackBounds;
  drsZones?: DRSZoneSegment[];
}