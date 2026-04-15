import type { TrackData, Point } from '../types/track-api.types';
import type { TrackFrame } from '../types/track.types';
import type { Frame } from '../types/api.types';

/**
 * Builds a canvas-ready `TrackData` object from a set of lightweight track frames
 * recorded during a reference lap. This is the primary track-building path used
 * for all current data.
 *
 * Processing steps:
 * 1. Extract (x, y) points from the frames to form the centre line.
 * 2. Remove duplicate consecutive points closer than 1 world unit apart.
 * 3. Close the loop by appending a copy of the first point when the gap between
 *    the first and last point exceeds 50 world units.
 * 4. Compute the axis-aligned bounding box.
 * 5. Generate inner and outer boundaries by offsetting the centre line ±75 units
 *    (half of the 150-unit track width) using smoothed normal vectors.
 * 6. Convert raw snake_case DRS zone indices to camelCase `DRSZoneSegment` objects.
 *
 * @param {TrackFrame[]} frames - Positional samples from the reference lap stored in Supabase.
 * @param {Array<{ start_index: number; end_index: number }>} [drsZones] - Optional raw DRS zone
 *   definitions; omitted when not available for the circuit or session type.
 * @returns {TrackData | null} The completed track geometry, or null if there are fewer than
 *   10 frames (insufficient data to build a meaningful circuit shape).
 */
export function buildTrackFromFrames(
  frames: TrackFrame[], 
  drsZones?: Array<{ start_index: number; end_index: number }>
): TrackData | null {
  if (!frames || frames.length < 10) {
    console.error('Not enough frames to build track');
    return null;
  }

  let centerLine: Point[] = frames.map(f => ({ x: f.x, y: f.y }));
  
  centerLine = removeDuplicates(centerLine);
  
  if (centerLine.length > 0) {
    const first = centerLine[0];
    const last = centerLine[centerLine.length - 1];
    const distance = Math.sqrt(
      Math.pow(last.x - first.x, 2) + Math.pow(last.y - first.y, 2)
    );
    
    if (distance > 50) {
      centerLine.push({ ...first });
    }
  }

  const xs = centerLine.map(p => p.x);
  const ys = centerLine.map(p => p.y);
  
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const trackWidth = 150;
  const innerBoundary = offsetPathImproved(centerLine, -trackWidth / 2);
  const outerBoundary = offsetPathImproved(centerLine, trackWidth / 2);

  const drsZoneSegments = drsZones?.map(zone => ({
    startIndex: zone.start_index,
    endIndex: zone.end_index
  }));

  return {
    innerBoundary,
    outerBoundary,
    centerLine,
    bounds: { minX, maxX, minY, maxY },
    drsZones: drsZoneSegments,
  };
}

/**
 * Removes consecutive duplicate points from a path by filtering out any point
 * whose Euclidean distance to the previous accepted point is below `threshold`.
 * This prevents degenerate zero-length segments that would produce NaN normals
 * in the boundary offset calculation.
 *
 * @param {Point[]} path - The input path to de-duplicate.
 * @param {number} [threshold=1.0] - Minimum distance (in world units) between
 *   consecutive accepted points.
 * @returns {Point[]} A new array with near-duplicate consecutive points removed.
 */
function removeDuplicates(path: Point[], threshold: number = 1.0): Point[] {
  if (path.length === 0) return path;
  
  const result: Point[] = [path[0]];
  
  for (let i = 1; i < path.length; i++) {
    const prev = result[result.length - 1];
    const curr = path[i];
    
    const dist = Math.sqrt(
      Math.pow(curr.x - prev.x, 2) + Math.pow(curr.y - prev.y, 2)
    );
    
    if (dist > threshold) {
      result.push(curr);
    }
  }
  
  return result;
}

/**
 * Generates an offset path (inner or outer boundary) from a centre-line path by
 * displacing each point along the local surface normal by `distance` world units.
 *
 * Normals are computed from a smoothed average tangent across a ±3 point window
 * (7 points total) rather than from adjacent points alone. This reduces boundary
 * kinking at high-curvature sections where per-point normals would be noisy.
 * Wrap-around indexing is used so the smoothing works correctly at the loop
 * join point.
 *
 * A positive `distance` offsets to the right of the direction of travel (outer
 * boundary); a negative `distance` offsets to the left (inner boundary).
 *
 * @param {Point[]} path - The centre-line path to offset. Must have at least 3 points.
 * @param {number} distance - Signed offset distance in world units.
 * @returns {Point[]} The offset boundary path with the same number of points as `path`.
 */
function offsetPathImproved(path: Point[], distance: number): Point[] {
  if (path.length < 3) return path;

  const offsetPoints: Point[] = [];
  const smoothingWindow = 3;

  for (let i = 0; i < path.length; i++) {
    const indices = [];
    for (let j = -smoothingWindow; j <= smoothingWindow; j++) {
      let idx = i + j;
      if (idx < 0) idx += path.length;
      if (idx >= path.length) idx -= path.length;
      indices.push(idx);
    }

    let avgDx = 0;
    let avgDy = 0;
    let count = 0;

    for (let j = 0; j < indices.length - 1; j++) {
      const p1 = path[indices[j]];
      const p2 = path[indices[j + 1]];
      
      avgDx += p2.x - p1.x;
      avgDy += p2.y - p1.y;
      count++;
    }

    avgDx /= count;
    avgDy /= count;

    const len = Math.sqrt(avgDx * avgDx + avgDy * avgDy) || 1;
    avgDx /= len;
    avgDy /= len;

    const nx = -avgDy;
    const ny = avgDx;

    const curr = path[i];
    offsetPoints.push({
      x: curr.x + nx * distance,
      y: curr.y + ny * distance,
    });
  }

  return offsetPoints;
}

/**
 * @deprecated Use `buildTrackFromFrames` instead. This function derives the
 * centre line from raw full-telemetry frames (lap 1 of the first driver) rather
 * than from dedicated lightweight track-shape frames. It is significantly slower,
 * produces lower-quality boundaries, and does not support DRS zones.
 *
 * Retained solely for backward compatibility with any code that has not yet
 * migrated to the new track-shape pipeline.
 *
 * @param {Frame[]} frames - Full telemetry frames for the race.
 * @returns {TrackData | null} A rough track geometry, or null if no valid data is found.
 */
export function extractTrackFromTelemetry(frames: Frame[]): TrackData | null {
  console.warn('Using legacy extractTrackFromTelemetry - consider using buildTrackFromFrames');
  
  if (!frames || frames.length === 0) {
    return null;
  }

  const allPoints: Point[] = [];
  const sampleRate = Math.max(1, Math.floor(frames.length / 500));
  
  for (let i = 0; i < frames.length; i += sampleRate) {
    const frame = frames[i];
    const drivers = Object.values(frame.drivers);
    
    for (const driver of drivers) {
      allPoints.push({ x: (driver as unknown as { x: number }).x, y: (driver as unknown as { x: number; y: number }).y });
    }
  }

  if (allPoints.length === 0) {
    return null;
  }

  const xs = allPoints.map(p => p.x);
  const ys = allPoints.map(p => p.y);
  
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const centerLine: Point[] = [];
  const firstFrame = frames[0];
  const firstDriverCode = Object.keys(firstFrame.drivers)[0];
  
  if (!firstDriverCode) {
    return null;
  }

  for (const frame of frames) {
    const driver = frame.drivers[firstDriverCode];
    if (driver && driver.lap === 1) {
      centerLine.push({ x: driver.x, y: driver.y });
    }
    
    if (driver && driver.lap > 1) {
      break;
    }
  }

  const trackWidth = 150;
  const innerBoundary = offsetPathImproved(centerLine, -trackWidth / 2);
  const outerBoundary = offsetPathImproved(centerLine, trackWidth / 2);

  return {
    innerBoundary,
    outerBoundary,
    centerLine,
    bounds: { minX, maxX, minY, maxY },
  };
}