import { useEffect, useRef, useState } from 'react';
import type { TrackData, Point } from '../../types/track.types';
import type { Frame } from '../../types/api.types';

interface AnimatedTrackCanvasProps {
  trackData?: TrackData;
  frames?: Frame[];
  driverColors?: Record<string, [number, number, number]>;
}

export default function AnimatedTrackCanvas({ 
  trackData, 
  frames,
  driverColors 
}: AnimatedTrackCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationRef = useRef<number | undefined>(undefined);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [fps] = useState(25); // Match backend FPS
  
  // Scaling state
  const scaleRef = useRef(1);
  const offsetXRef = useRef(0);
  const offsetYRef = useRef(0);

  // Calculate scaling when track data changes
  useEffect(() => {
    if (!trackData || !canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const bounds = trackData.bounds;
    const padding = 50;

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
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Animation loop
  useEffect(() => {
    if (!frames || frames.length === 0) return;

    let lastTime = performance.now();
    const frameTime = 1000 / fps;

    const animate = (currentTime: number) => {
      const deltaTime = currentTime - lastTime;

      if (deltaTime >= frameTime) {
        setCurrentFrame(prev => (prev + 1) % frames.length);
        lastTime = currentTime;
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [frames, fps]);

  // Draw loop
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

    // Draw finish line
    if (trackData.innerBoundary.length > 0) {
      const innerStart = worldToScreen(trackData.innerBoundary[0]);
      const outerStart = worldToScreen(trackData.outerBoundary[0]);
      
      const numSquares = 20;
      for (let i = 0; i < numSquares; i++) {
        const t1 = i / numSquares;
        const t2 = (i + 1) / numSquares;
        
        const x1 = innerStart.x + t1 * (outerStart.x - innerStart.x);
        const y1 = innerStart.y + t1 * (outerStart.y - innerStart.y);
        const x2 = innerStart.x + t2 * (outerStart.x - innerStart.x);
        const y2 = innerStart.y + t2 * (outerStart.y - innerStart.y);
        
        ctx.strokeStyle = i % 2 === 0 ? '#FFFFFF' : '#000000';
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    }

    // Draw drivers
    if (frames && frames[currentFrame]) {
      const frame = frames[currentFrame];
      const drivers = frame.drivers;

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
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(code, screenPos.x, screenPos.y - 10);
      }
    }

    // Draw frame info
    if (frames && frames[currentFrame]) {
      const frame = frames[currentFrame];
      ctx.fillStyle = '#FFFFFF';
      ctx.font = '16px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`Lap: ${frame.lap}`, 20, 30);
      ctx.fillText(`Frame: ${currentFrame + 1}/${frames.length}`, 20, 50);
      ctx.fillText(`Time: ${frame.t.toFixed(1)}s`, 20, 70);
    }

  }, [trackData, frames, currentFrame, driverColors]);

  return (
    <div ref={containerRef} style={{ 
      position: 'relative',
      width: '100%',
      height: '100%',
      backgroundColor: '#000',
      overflow: 'hidden'
    }}>
      <canvas 
        ref={canvasRef} 
        style={{ 
          display: 'block',
          width: '100%',
          height: '100%'
        }} 
      />
      {!trackData && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          color: '#fff',
          textAlign: 'center',
          fontSize: '18px'
        }}>
          <p>Loading track data...</p>
        </div>
      )}
    </div>
  );
}
