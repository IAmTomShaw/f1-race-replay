import { useEffect, useRef, useCallback } from 'react';
import type { TrackData, Point } from '../../../types/track.types';
import type { Frame } from '../../../types/api.types';
import './index.css';

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

const ZOOM_MIN    = 1;
const ZOOM_MAX    = 5;
const FOLLOW_ZOOM = 5;
const HIT_RADIUS  = 12;

export default function AnimatedTrackCanvas({
  trackData, frames, driverColors, currentFrame, interpolatedFrame,
  leaderCode, focusedDrivers, comparisonMode,
  comparisonPositions, comparisonDriverColor,
}: AnimatedTrackCanvasProps) {
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const scaleRef        = useRef<number>(1);
  const offsetXRef      = useRef<number>(0);
  const offsetYRef      = useRef<number>(0);
  const dprRef          = useRef<number>(1);
  const optimalAngleRef = useRef<number>(0);
  const centroidRef     = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const zoomRef        = useRef<number>(1);
  const panXRef        = useRef<number>(0);
  const panYRef        = useRef<number>(0);
  const isDragging     = useRef<boolean>(false);
  const dragStart      = useRef<{ x: number; y: number; panX: number; panY: number }>({ x: 0, y: 0, panX: 0, panY: 0 });
  const followedDriver = useRef<string | null>(null);

  const worldToScreen = useCallback((point: Point): Point => {
    const { x: cx, y: cy } = centroidRef.current;
    const cos = Math.cos(optimalAngleRef.current);
    const sin = Math.sin(optimalAngleRef.current);
    const dx = point.x - cx, dy = point.y - cy;
    const rx = cos * dx - sin * dy, ry = sin * dx + cos * dy;
    return {
      x: -ry * scaleRef.current + offsetXRef.current,
      y: -rx * scaleRef.current + offsetYRef.current,
    };
  }, []);

  const calculateScaling = useCallback(() => {
    if (!trackData || !canvasRef.current) return;
    const canvas  = canvasRef.current;
    const padding = 40;
    const availableWidth  = canvas.width  / dprRef.current - 2 * padding;
    const availableHeight = canvas.height / dprRef.current - 2 * padding;

    const points = [...trackData.outerBoundary, ...trackData.innerBoundary];
    if (points.length === 0) return;

    const { bounds } = trackData;
    const cx = (bounds.maxX + bounds.minX) / 2;
    const cy = (bounds.maxY + bounds.minY) / 2;
    centroidRef.current = { x: cx, y: cy };

    let bestScale = 0, bestAngle = 0;
    for (let deg = 0; deg < 180; deg++) {
      const rad = (deg * Math.PI) / 180;
      const cos = Math.cos(rad), sin = Math.sin(rad);
      let minRX = Infinity, maxRX = -Infinity, minRY = Infinity, maxRY = -Infinity;
      for (const p of points) {
        const dx = p.x - cx, dy = p.y - cy;
        const rx = cos * dx - sin * dy, ry = sin * dx + cos * dy;
        if (rx < minRX) minRX = rx; if (rx > maxRX) maxRX = rx;
        if (ry < minRY) minRY = ry; if (ry > maxRY) maxRY = ry;
      }
      const scale = Math.min(availableWidth / (maxRY - minRY), availableHeight / (maxRX - minRX));
      if (scale > bestScale) { bestScale = scale; bestAngle = rad; }
    }

    optimalAngleRef.current = bestAngle;
    scaleRef.current        = bestScale;

    const cos = Math.cos(bestAngle), sin = Math.sin(bestAngle);
    let minRX = Infinity, maxRX = -Infinity, minRY = Infinity, maxRY = -Infinity;
    for (const p of points) {
      const dx = p.x - cx, dy = p.y - cy;
      const rx = cos * dx - sin * dy, ry = sin * dx + cos * dy;
      if (rx < minRX) minRX = rx; if (rx > maxRX) maxRX = rx;
      if (ry < minRY) minRY = ry; if (ry > maxRY) maxRY = ry;
    }

    const cssWidth  = canvas.width  / dprRef.current;
    const cssHeight = canvas.height / dprRef.current;
    offsetXRef.current = cssWidth  / 2 + (maxRY + minRY) / 2 * bestScale;
    offsetYRef.current = cssHeight / 2 + (maxRX + minRX) / 2 * bestScale;
  }, [trackData]);

  // ── Core draw ─────────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !trackData) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const frameToRender = interpolatedFrame || (frames && frames[currentFrame]);

    if (followedDriver.current && frameToRender) {
      const pos = frameToRender.drivers[followedDriver.current];
      if (pos) {
        const base = worldToScreen({ x: pos.x, y: pos.y });
        const w    = canvas.width  / dprRef.current;
        const h    = canvas.height / dprRef.current;
        panXRef.current = w / 2 - base.x * zoomRef.current;
        panYRef.current = h / 2 - base.y * zoomRef.current;
      }
    }

    const drawPath = (points: Point[], color: string, lineWidth: number) => {
      if (points.length < 2) return;
      ctx.strokeStyle = color;
      ctx.lineWidth   = lineWidth;
      ctx.lineJoin    = 'round';
      ctx.lineCap     = 'round';
      ctx.beginPath();
      const first = worldToScreen(points[0]);
      ctx.moveTo(first.x, first.y);
      for (let i = 1; i < points.length; i++) {
        const p = worldToScreen(points[i]);
        ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
    };

    const drawStar = (cx: number, cy: number, outerR: number, innerR: number) => {
      ctx.beginPath();
      for (let i = 0; i < 10; i++) {
        const r     = i % 2 === 0 ? outerR : innerR;
        const angle = (Math.PI / 5) * i - Math.PI / 2;
        const x = cx + r * Math.cos(angle), y = cy + r * Math.sin(angle);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = '#FFD700';
      ctx.fill();
    };

    const w = canvas.width  / dprRef.current;
    const h = canvas.height / dprRef.current;

    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, w, h);

    ctx.save();
    ctx.translate(panXRef.current, panYRef.current);
    ctx.scale(zoomRef.current, zoomRef.current);

    // Track
    drawPath(trackData.outerBoundary, '#666666', 3);
    drawPath(trackData.innerBoundary, '#666666', 3);

    if (trackData.drsZones) {
      for (const zone of trackData.drsZones) {
        const seg = trackData.outerBoundary.slice(zone.startIndex, zone.endIndex + 1);
        if (seg.length > 1) drawPath(seg, '#00FF00', 6);
      }
    }

    // Finish line
    if (trackData.innerBoundary.length > 0 && trackData.outerBoundary.length > 0) {
      const innerStart = worldToScreen(trackData.innerBoundary[0]);
      const outerStart = worldToScreen(trackData.outerBoundary[0]);
      const dx = outerStart.x - innerStart.x, dy = outerStart.y - innerStart.y;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len > 0) {
        const ex = (dx / len) * 16, ey = (dy / len) * 16;
        const ei = { x: innerStart.x - ex, y: innerStart.y - ey };
        const eo = { x: outerStart.x + ex, y: outerStart.y + ey };
        for (let i = 0; i < 20; i++) {
          const t1 = i / 20, t2 = (i + 1) / 20;
          ctx.strokeStyle = i % 2 === 0 ? '#FFFFFF' : '#000000';
          ctx.lineWidth = 5;
          ctx.beginPath();
          ctx.moveTo(ei.x + t1 * (eo.x - ei.x), ei.y + t1 * (eo.y - ei.y));
          ctx.lineTo(ei.x + t2 * (eo.x - ei.x), ei.y + t2 * (eo.y - ei.y));
          ctx.stroke();
        }
      }
    }

    // ── Drivers (normal mode only) ────────────────────────────────────────
    if (frameToRender && !comparisonMode) {
      const derivedLeaderCode = leaderCode;

      const anyFocused = (focusedDrivers?.size ?? 0) > 0;

      // Ghost pass
      for (const [code, pos] of Object.entries(frameToRender.drivers)) {
        if (!anyFocused || focusedDrivers!.has(code)) continue;
        const sp    = worldToScreen({ x: pos.x, y: pos.y });
        const color = driverColors?.[code] || [255, 255, 255];
        ctx.globalAlpha = 0.15;
        ctx.fillStyle   = `rgb(${color[0]},${color[1]},${color[2]})`;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      // Active pass
      for (const [code, pos] of Object.entries(frameToRender.drivers)) {
        if (anyFocused && !focusedDrivers!.has(code)) continue;
        const sp       = worldToScreen({ x: pos.x, y: pos.y });
        const isOut    = pos.is_out === true;
        const color    = driverColors?.[code] || [255, 255, 255];
        const dotColor = isOut ? 'rgba(255,255,255,0.5)' : `rgb(${color[0]},${color[1]},${color[2]})`;

        if (code === followedDriver.current) {
          ctx.strokeStyle = dotColor;
          ctx.lineWidth   = 1.5;
          ctx.beginPath();
          ctx.arc(sp.x, sp.y, 9, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.fillStyle = dotColor;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 5, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle    = isOut ? 'rgba(255,255,255,0.5)' : '#FFFFFF';
        ctx.font         = 'bold 8px sans-serif';
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(code, sp.x, sp.y - 10);
      }

      if (derivedLeaderCode && frameToRender.drivers[derivedLeaderCode]) {
        if (!anyFocused || focusedDrivers!.has(derivedLeaderCode)) {
          const lp = worldToScreen({
            x: frameToRender.drivers[derivedLeaderCode].x,
            y: frameToRender.drivers[derivedLeaderCode].y,
          });
          drawStar(lp.x, lp.y - 22, 5, 2.5);
        }
      }
    }

    // ── Comparison dots ───────────────────────────────────────────────────
    if (comparisonMode && comparisonPositions && comparisonPositions.length > 0) {
      const [r, g, b] = comparisonDriverColor ?? [255, 255, 255];

      for (const { year, x, y, is_retired } of comparisonPositions) {
        const sp = worldToScreen({ x, y });
        const color = is_retired ? 'rgb(100,100,100)' : `rgb(${r},${g},${b})`;
        const labelColor = is_retired ? 'rgba(255,255,255,0.4)' : '#FFFFFF';

        // Outer ring
        ctx.strokeStyle = color;
        ctx.lineWidth   = 1.5;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 8, 0, Math.PI * 2);
        ctx.stroke();

        // Inner dot
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 4, 0, Math.PI * 2);
        ctx.fill();

        // Year label
        ctx.fillStyle    = labelColor;
        ctx.font         = 'bold 7px sans-serif';
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(year), sp.x, sp.y - 14);
      }
    }

    ctx.restore();
  }, [trackData, frames, currentFrame, driverColors, interpolatedFrame,
      focusedDrivers, worldToScreen, comparisonMode,
      comparisonPositions, comparisonDriverColor]);

  useEffect(() => { draw(); }, [draw]);

  // ── Resize ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const handleResize = () => {
      if (!canvasRef.current || !containerRef.current) return;
      const dpr = window.devicePixelRatio || 1;
      dprRef.current = dpr;
      canvasRef.current.width  = containerRef.current.clientWidth  * dpr;
      canvasRef.current.height = containerRef.current.clientHeight * dpr;
      const ctx = canvasRef.current.getContext('2d');
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
      calculateScaling();
      draw();
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [calculateScaling, draw]);

  useEffect(() => { calculateScaling(); }, [calculateScaling]);

  // ── Wheel zoom ────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      followedDriver.current = null;
      const rect    = canvas.getBoundingClientRect();
      const mouseX  = e.clientX - rect.left;
      const mouseY  = e.clientY - rect.top;
      const factor  = e.deltaY < 0 ? 1.1 : 0.9;
      const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomRef.current * factor));
      const ratio   = newZoom / zoomRef.current;
      panXRef.current = mouseX - (mouseX - panXRef.current) * ratio;
      panYRef.current = mouseY - (mouseY - panYRef.current) * ratio;
      zoomRef.current = newZoom;
      draw();
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [draw]);

  // ── Pan + click follow ────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      isDragging.current = true;
      dragStart.current  = { x: e.clientX, y: e.clientY, panX: panXRef.current, panY: panYRef.current };
      canvas.style.cursor = 'grabbing';
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) followedDriver.current = null;
      panXRef.current = dragStart.current.panX + dx;
      panYRef.current = dragStart.current.panY + dy;
      draw();
    };

    const onMouseUp = (e: MouseEvent) => {
      isDragging.current  = false;
      canvas.style.cursor = 'grab';

      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) return;

      // Don't handle driver-follow clicks in comparison mode
      if (comparisonMode) return;

      const rect   = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const baseX  = (mouseX - panXRef.current) / zoomRef.current;
      const baseY  = (mouseY - panYRef.current) / zoomRef.current;

      const frameToRender = interpolatedFrame || (frames && frames[currentFrame]);
      if (!frameToRender) return;

      let closest: string | null = null;
      let closestDist = HIT_RADIUS;
      for (const [code, pos] of Object.entries(frameToRender.drivers)) {
        const sp   = worldToScreen({ x: pos.x, y: pos.y });
        const dist = Math.sqrt((sp.x - baseX) ** 2 + (sp.y - baseY) ** 2);
        if (dist < closestDist) { closestDist = dist; closest = code; }
      }

      if (closest) {
        if (followedDriver.current === closest) {
          followedDriver.current = null;
          zoomRef.current = 1;
          panXRef.current = 0;
          panYRef.current = 0;
        } else {
          followedDriver.current = closest;
          zoomRef.current = FOLLOW_ZOOM;
          panXRef.current = 0;
          panYRef.current = 0;
        }
      }
      draw();
    };

    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup',   onMouseUp);
    canvas.style.cursor = 'grab';

    return () => {
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup',   onMouseUp);
    };
  }, [draw, frames, currentFrame, interpolatedFrame, worldToScreen, comparisonMode]);

  // ── Reset ─────────────────────────────────────────────────────────────────
  const handleResetCamera = () => {
    followedDriver.current = null;
    zoomRef.current = 1;
    panXRef.current = 0;
    panYRef.current = 0;
    draw();
  };

  return (
    <div ref={containerRef} className="animated-track-canvas-container">
      <canvas ref={canvasRef} className="animated-track-canvas" />
      {!trackData && (
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
