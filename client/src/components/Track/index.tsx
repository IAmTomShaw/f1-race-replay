import { useEffect, useRef, useCallback } from 'react';
import type { TrackData, Point } from '../../types/track.types';
import type { Frame } from '../../types/api.types';
import './index.css';

interface AnimatedTrackCanvasProps {
  trackData?: TrackData | null;
  frames?: Frame[];
  driverColors?: Record<string, [number, number, number]>;
  currentFrame: number;
  interpolatedFrame?: Frame | null;
}

export default function AnimatedTrackCanvas({ 
  trackData, 
  frames,
  driverColors,
  currentFrame,
  interpolatedFrame
}: AnimatedTrackCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Scaling state
  const scaleRef = useRef<number>(1);
  const offsetXRef = useRef<number>(0);
  const offsetYRef = useRef<number>(0);

  // Calculate scaling
  const calculateScaling = useCallback(() => {
    if (!trackData || !canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const bounds = trackData.bounds;
    const padding = 80; // Increased from 50 to 80 for better fit

    const worldWidth = bounds.maxX - bounds.minX;
    const worldHeight = bounds.maxY - bounds.minY;

    const availableWidth = canvas.width - 2 * padding;
    const availableHeight = canvas.height - 2 * padding;

    const scaleX = availableWidth / worldWidth;
    const scaleY = availableHeight / worldHeight;
    scaleRef.current = Math.min(scaleX, scaleY);

    const scaledWidth = worldWidth * scaleRef.current;
    const scaledHeight = worldHeight * scaleRef.current;

    offsetXRef.current = (canvas.width - scaledWidth) / 2 - bounds.minX * scaleRef.current;
    offsetYRef.current = (canvas.height - scaledHeight) / 2 - bounds.minY * scaleRef.current;
  }, [trackData]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (!canvasRef.current || !containerRef.current) return;
      const container = containerRef.current;
      canvasRef.current.width = container.clientWidth;
      canvasRef.current.height = container.clientHeight;
      calculateScaling();
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [calculateScaling]);

  // Recalculate scaling when track data changes
  useEffect(() => {
    calculateScaling();
  }, [calculateScaling]);

  // Draw loop - redraws whenever currentFrame changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !trackData) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const worldToScreen = (point: Point): Point => ({
      x: point.x * scaleRef.current + offsetXRef.current,
      y: point.y * scaleRef.current + offsetYRef.current,
    });

    // Clear canvas
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw track boundaries
    const drawPath = (points: Point[], color: string, lineWidth: number) => {
      if (points.length < 2) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      ctx.beginPath();
      const first = worldToScreen(points[0]);
      ctx.moveTo(first.x, first.y);
      for (let i = 1; i < points.length; i++) {
        const p = worldToScreen(points[i]);
        ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
    };

    drawPath(trackData.outerBoundary, '#666666', 4);
    drawPath(trackData.innerBoundary, '#666666', 4);

    // Draw DRS zones
    if (trackData.drsZones) {
      for (const zone of trackData.drsZones) {
        const segment = trackData.outerBoundary.slice(zone.startIndex, zone.endIndex + 1);
        if (segment.length > 1) {
          drawPath(segment, '#00FF00', 8);
        }
      }
    }

    // Draw finish line (checkered)
    if (trackData.innerBoundary.length > 0 && trackData.outerBoundary.length > 0) {
      const innerStart = worldToScreen(trackData.innerBoundary[0]);
      const outerStart = worldToScreen(trackData.outerBoundary[0]);
      
      const dx = outerStart.x - innerStart.x;
      const dy = outerStart.y - innerStart.y;
      const length = Math.sqrt(dx * dx + dy * dy);
      
      if (length > 0) {
        const extension = 20;
        const extendX = (dx / length) * extension;
        const extendY = (dy / length) * extension;

        const extendedInner = {
          x: innerStart.x - extendX,
          y: innerStart.y - extendY,
        };

        const extendedOuter = {
          x: outerStart.x + extendX,
          y: outerStart.y + extendY,
        };

        const numSquares = 20;
        for (let i = 0; i < numSquares; i++) {
          const t1 = i / numSquares;
          const t2 = (i + 1) / numSquares;
          
          const x1 = extendedInner.x + t1 * (extendedOuter.x - extendedInner.x);
          const y1 = extendedInner.y + t1 * (extendedOuter.y - extendedInner.y);
          const x2 = extendedInner.x + t2 * (extendedOuter.x - extendedInner.x);
          const y2 = extendedInner.y + t2 * (extendedOuter.y - extendedInner.y);
          
          ctx.strokeStyle = i % 2 === 0 ? '#FFFFFF' : '#000000';
          ctx.lineWidth = 6;
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        }
      }
    }

    // Draw drivers (use interpolated frame if available)
    const frameToRender = interpolatedFrame || (frames && frames[currentFrame]);
    
    if (frameToRender) {
      const drivers = frameToRender.drivers;

      for (const [code, pos] of Object.entries(drivers)) {
        const screenPos = worldToScreen({ x: pos.x, y: pos.y });
        
        // Get driver color
        const color = driverColors?.[code] || [255, 255, 255];
        const colorStr = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;

        // Draw driver dot
        ctx.fillStyle = colorStr;
        ctx.beginPath();
        ctx.arc(screenPos.x, screenPos.y, 6, 0, Math.PI * 2);
        ctx.fill();

        // Draw driver code label
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(code, screenPos.x, screenPos.y - 12);
      }
    }

  }, [trackData, frames, currentFrame, driverColors, interpolatedFrame]);

  return (
    <div ref={containerRef} className="animated-track-canvas-container">
      <canvas ref={canvasRef} className="animated-track-canvas" />
      
      {!trackData && (
        <div className="track-loading-placeholder">
          <p>Loading track data...</p>
        </div>
      )}
    </div>
  );
}
