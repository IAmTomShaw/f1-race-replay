import type { TrackData, Point } from "../types/track-api.types";
import "../styles/variables.css";

/**
 * An imperative canvas-based renderer for static circuit geometry.
 * Handles scaling, coordinate projection, and drawing of track boundaries,
 * DRS zones, and the checkered finish line.
 *
 * This class is used for contexts where a standalone canvas renderer is needed
 * outside of the React component tree. For the live replay view, the equivalent
 * logic lives in `AnimatedTrackCanvas` and `useAnimatedTrackCanvas`.
 */
export class TrackRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private trackData: TrackData | null = null;
  private scale: number = 1;
  private offsetX: number = 0;
  private offsetY: number = 0;

  /**
   * Creates a new `TrackRenderer` bound to the given canvas element.
   *
   * @param {HTMLCanvasElement} canvas - The canvas element to render into.
   * @throws {Error} If a 2D rendering context cannot be obtained from the canvas.
   */
  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Could not get canvas context');
    }
    this.ctx = ctx;
  }

  /**
   * Stores the track geometry and immediately recalculates the scale and offset
   * values so the new circuit fits the current canvas size.
   *
   * @param {TrackData} data - The circuit geometry to render.
   */
  setTrackData(data: TrackData) {
    this.trackData = data;
    this.calculateScaling();
  }

  /**
   * Computes `scale`, `offsetX`, and `offsetY` so the track geometry fills the
   * canvas with uniform 50-pixel padding on all sides, maintaining aspect ratio.
   *
   * The Y-axis is inverted during offset calculation because the canvas coordinate
   * system has Y increasing downward, while the telemetry world space has Y
   * increasing upward. `offsetY` is anchored to `bounds.maxY` so that negating Y
   * in `worldToScreen` produces the correct orientation.
   */
  private calculateScaling() {
    if (!this.trackData) return;

    const bounds = this.trackData.bounds;
    const padding = 50;

    const worldWidth  = bounds.maxX - bounds.minX;
    const worldHeight = bounds.maxY - bounds.minY;

    const availableWidth  = this.canvas.width  - 2 * padding;
    const availableHeight = this.canvas.height - 2 * padding;

    const scaleX = availableWidth  / worldWidth;
    const scaleY = availableHeight / worldHeight;
    this.scale = Math.min(scaleX, scaleY);

    const scaledWidth  = worldWidth  * this.scale;
    const scaledHeight = worldHeight * this.scale;

    this.offsetX = (this.canvas.width  - scaledWidth)  / 2 - bounds.minX * this.scale;
    this.offsetY = (this.canvas.height + scaledHeight) / 2 + bounds.minY * this.scale;
  }

  /**
   * Projects a world-space point to canvas pixel coordinates.
   * Negates the Y component to account for the Y-up (world) vs Y-down (canvas) mismatch.
   *
   * @param {Point} point - World-space coordinate to transform.
   * @returns {Point} Corresponding canvas pixel position.
   */
  private worldToScreen(point: Point): Point {
    return {
      x:  point.x * this.scale + this.offsetX,
      y: -point.y * this.scale + this.offsetY,
    };
  }

  /**
   * Fills the entire canvas with a solid black background.
   * Should be called at the start of each render pass to prevent frame ghosting.
   */
  clear() {
    this.ctx.fillStyle = '#000000';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  /**
   * Performs a full render pass: clears the canvas then draws the outer boundary,
   * inner boundary, DRS zones, and finish line in order.
   * No-ops when `trackData` has not been set.
   */
  render() {
    if (!this.trackData) return;

    this.clear();

    this.drawPath(this.trackData.outerBoundary, '#666666', 1);
    this.drawPath(this.trackData.innerBoundary, '#666666', 1);
    this.drawDRSZones();
    this.drawFinishLine();
  }

  /**
   * Draws each DRS zone as a thick green overlay on the outer boundary segment
   * defined by `[startIndex, endIndex]`. Zones whose indices fall outside the
   * outer boundary array are skipped with a console warning.
   */
  private drawDRSZones() {
    if (!this.trackData) {
      return;
    }

    if (!this.trackData.drsZones || this.trackData.drsZones.length === 0) {
      return;
    }

    const drsColor = '#00FF00';

    for (let i = 0; i < this.trackData.drsZones.length; i++) {
      const zone = this.trackData.drsZones[i];
      const { startIndex: startIdx, endIndex: endIdx } = zone;

      if (startIdx >= this.trackData.outerBoundary.length || endIdx >= this.trackData.outerBoundary.length) {
        continue;
      }

      const zoneSegment = this.trackData.outerBoundary.slice(startIdx, endIdx + 1);

      if (zoneSegment.length < 2) {
        continue;
      }

      this.ctx.strokeStyle = drsColor;
      this.ctx.lineWidth = 8;
      this.ctx.setLineDash([]);

      this.ctx.beginPath();
      const firstPoint = this.worldToScreen(zoneSegment[0]);
      this.ctx.moveTo(firstPoint.x, firstPoint.y);
      for (let j = 1; j < zoneSegment.length; j++) {
        const sp = this.worldToScreen(zoneSegment[j]);
        this.ctx.lineTo(sp.x, sp.y);
      }
      this.ctx.stroke();
    }
  }

  /**
   * Draws a polyline through an array of world-space points.
   *
   * @param {Point[]} points - World-space vertices of the path to draw.
   * @param {string} color - CSS stroke color.
   * @param {number} lineWidth - Stroke width in canvas pixels.
   * @param {boolean} [dashed=false] - When true, renders a [5, 5] dashed line.
   */
  private drawPath(points: Point[], color: string, lineWidth: number, dashed = false) {
    if (points.length < 2) return;

    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = lineWidth;
    this.ctx.setLineDash(dashed ? [5, 5] : []);

    this.ctx.beginPath();
    const first = this.worldToScreen(points[0]);
    this.ctx.moveTo(first.x, first.y);
    for (let i = 1; i < points.length; i++) {
      const sp = this.worldToScreen(points[i]);
      this.ctx.lineTo(sp.x, sp.y);
    }
    this.ctx.stroke();
    this.ctx.setLineDash([]);
  }

  /**
   * Draws a 20-segment alternating black-and-white checkered finish line between
   * the first point of the inner and outer boundary, extended 20 pixels beyond
   * each edge for visual clarity.
   *
   * No-ops when the inner boundary is empty or the computed line length is zero.
   */
  private drawFinishLine() {
    if (!this.trackData || this.trackData.innerBoundary.length === 0) return;

    const innerStart = this.worldToScreen(this.trackData.innerBoundary[0]);
    const outerStart = this.worldToScreen(this.trackData.outerBoundary[0]);

    const dx = outerStart.x - innerStart.x;
    const dy = outerStart.y - innerStart.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    if (length === 0) return;

    const extension = 20;
    const extendX = (dx / length) * extension;
    const extendY = (dy / length) * extension;

    const extendedInner = { x: innerStart.x - extendX, y: innerStart.y - extendY };
    const extendedOuter = { x: outerStart.x + extendX, y: outerStart.y + extendY };

    const numSquares = 20;
    const stepX = (extendedOuter.x - extendedInner.x) / numSquares;
    const stepY = (extendedOuter.y - extendedInner.y) / numSquares;

    for (let i = 0; i < numSquares; i++) {
      this.ctx.strokeStyle = i % 2 === 0 ? '#FFFFFF' : '#000000';
      this.ctx.lineWidth = 6;
      this.ctx.beginPath();
      this.ctx.moveTo(extendedInner.x + stepX * i,       extendedInner.y + stepY * i);
      this.ctx.lineTo(extendedInner.x + stepX * (i + 1), extendedInner.y + stepY * (i + 1));
      this.ctx.stroke();
    }
  }

  /**
   * Resizes the canvas to the given dimensions, recalculates scaling to fit
   * the current track geometry, and triggers a full re-render.
   * Should be called whenever the container element changes size.
   *
   * @param {number} width - New canvas width in pixels.
   * @param {number} height - New canvas height in pixels.
   */
  resize(width: number, height: number) {
    this.canvas.width  = width;
    this.canvas.height = height;
    this.calculateScaling();
    this.render();
  }
}