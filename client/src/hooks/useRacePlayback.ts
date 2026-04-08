import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import type { Frame, DriverPosition } from '../types/api.types';

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function useRacePlayback(frames: Frame[], totalLaps?: number) {
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [interpolatedFrame, setInterpolatedFrame] = useState<Frame | null>(null);
  const [isPaused, setIsPaused]           = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const framePositionRef = useRef<number>(0);
  const animationRef     = useRef<number | undefined>(undefined);

  const lapFrameIndices = useMemo(() => {
    if (!totalLaps || frames.length === 0) return [];
    const indices: number[] = [];
    for (let lap = 1; lap <= totalLaps; lap++) {
      const idx = frames.findIndex(f => f.lap >= lap);
      indices.push(idx === -1 ? frames.length - 1 : idx);
    }
    return indices;
  }, [frames, totalLaps]);

  const handlePlayPause   = useCallback(() => setIsPaused(p => !p), []);
  const handleSpeedChange = useCallback((s: number) => setPlaybackSpeed(s), []);

  const handleSeek = useCallback((frame: number) => {
    framePositionRef.current = Math.max(0, Math.min(frame, frames.length - 1));
    setCurrentFrameIndex(Math.floor(framePositionRef.current));
  }, [frames]);

  const handleSeekToLap = useCallback((lap: number) => {
    const clamped  = Math.max(1, Math.min(lap, totalLaps ?? 1));
    const frameIdx = lapFrameIndices[clamped - 1] ?? 0;
    handleSeek(frameIdx);
  }, [lapFrameIndices, totalLaps, handleSeek]);

  const handleRestart = useCallback(() => {
    framePositionRef.current = 0;
    setCurrentFrameIndex(0);
    setIsPaused(false);
  }, []);

  // ── Animation loop ───────────────────────────────────────────────────────
  useEffect(() => {
    if (frames.length === 0) return;
    let lastTime = performance.now();

    const animate = (currentTime: number) => {
      if (!isPaused) {
        const delta = (currentTime - lastTime) / 1000;
        framePositionRef.current += delta * playbackSpeed;

        if (framePositionRef.current >= frames.length - 1) {
          framePositionRef.current = frames.length - 1;
          setIsPaused(true);
        }
        if (framePositionRef.current < 0) framePositionRef.current = 0;

        const fi  = Math.floor(framePositionRef.current);
        const fi2 = Math.min(fi + 1, frames.length - 1);
        const t   = framePositionRef.current - fi;
        const f1  = frames[fi], f2 = frames[fi2];

        const interpolatedDrivers: Record<string, DriverPosition> = {};
        for (const code of Object.keys(f1.drivers)) {
          if (code in f2.drivers) {
            const p1 = f1.drivers[code], p2 = f2.drivers[code];
            interpolatedDrivers[code] = {
              x:         lerp(p1.x,        p2.x,        t),
              y:         lerp(p1.y,        p2.y,        t),
              dist:      lerp(p1.dist,     p2.dist,     t),
              lap:       p1.lap,
              rel_dist:  lerp(p1.rel_dist, p2.rel_dist, t),
              tyre:      p1.tyre,
              position:  p1.position,
              speed:     lerp(p1.speed,    p2.speed,    t),
              gear:      p1.gear,
              drs:       p1.drs,
              throttle:  lerp(p1.throttle, p2.throttle, t),
              brake:     lerp(p1.brake,    p2.brake,    t),
              is_out:    p1.is_out,
              finished:  p1.finished,
            };
          } else {
            interpolatedDrivers[code] = f1.drivers[code];
          }
        }

        setCurrentFrameIndex(fi);
        setInterpolatedFrame({
          t: lerp(f1.t, f2.t, t), lap: f1.lap,
          drivers: interpolatedDrivers, weather: f1.weather,
        });
        lastTime = currentTime;
      }
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => { if (animationRef.current) cancelAnimationFrame(animationRef.current); };
  }, [frames, isPaused, playbackSpeed]);

  // ── Keyboard shortcuts ───────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case ' ':           e.preventDefault(); handlePlayPause(); break;
        case 'ArrowLeft':   e.preventDefault(); handleSeek(Math.floor(framePositionRef.current) - 25); break;
        case 'ArrowRight':  e.preventDefault(); handleSeek(Math.floor(framePositionRef.current) + 25); break;
        case 'ArrowUp':     e.preventDefault(); handleSpeedChange(Math.min(8,   playbackSpeed * 2)); break;
        case 'ArrowDown':   e.preventDefault(); handleSpeedChange(Math.max(0.1, playbackSpeed / 2)); break;
        case 'r': case 'R': e.preventDefault(); handleRestart(); break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [playbackSpeed, handlePlayPause, handleSeek, handleRestart, handleSpeedChange]);

  const displayFrame = interpolatedFrame || frames[currentFrameIndex] || null;
  const totalTime    = frames[frames.length - 1]?.t ?? 0;

  return {
    currentFrameIndex,
    interpolatedFrame,
    isPaused,
    playbackSpeed,
    lapFrameIndices,
    displayFrame,
    totalTime,
    framePositionRef,
    handlePlayPause,
    handleSpeedChange,
    handleSeek,
    handleSeekToLap,
    handleRestart,
  };
}
