import { useState, useEffect, useRef, useCallback } from 'react';
import AnimatedTrackCanvas from '../Track';
import PlaybackControls from '../PlaybackControls';
import type { TrackData } from '../../../types/track.types';
import type { Frame, DriverPosition } from '../../../types/api.types';
import './index.css';
import Leaderboard from '../Leaderboard';
import SessionBanner from '../SessionBanner';

interface RaceViewerProps {
  trackData: TrackData;
  frames: Frame[];
  driverColors: Record<string, [number, number, number]>;
  driverTeams: Record<string, string>;
  eventName?: string;
  circuitName?: string;
  country?: string;
  year?: number;
  onPrevRace?: () => void;
  onNextRace?: () => void;
  hasPrevRace?: boolean;
  hasNextRace?: boolean;
}

export default function RaceViewer({
  trackData,
  frames,
  driverColors,
  driverTeams,
  eventName,
  circuitName,
  country,
  year,
  onPrevRace,
  onNextRace,
  hasPrevRace = false,
  hasNextRace = false,
}: RaceViewerProps) {
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [interpolatedFrame, setInterpolatedFrame] = useState<Frame | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const framePositionRef = useRef<number>(0);

  const handlePlayPause = useCallback(() => setIsPaused(prev => !prev), []);
  const handleSpeedChange = useCallback((speed: number) => setPlaybackSpeed(speed), []);

  const handleSeek = useCallback((frame: number) => {
    framePositionRef.current = Math.max(0, Math.min(frame, frames.length - 1));
    setCurrentFrameIndex(Math.floor(framePositionRef.current));
  }, [frames]);

  const handleRestart = useCallback(() => {
    framePositionRef.current = 0;
    setCurrentFrameIndex(0);
    setIsPaused(true);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case ' ':       e.preventDefault(); handlePlayPause(); break;
        case 'ArrowLeft':  e.preventDefault(); handleSeek(Math.floor(framePositionRef.current) - 25); break;
        case 'ArrowRight': e.preventDefault(); handleSeek(Math.floor(framePositionRef.current) + 25); break;
        case 'ArrowUp':    e.preventDefault(); handleSpeedChange(Math.min(8, playbackSpeed * 2)); break;
        case 'ArrowDown':  e.preventDefault(); handleSpeedChange(Math.max(0.1, playbackSpeed / 2)); break;
        case 'r': case 'R': e.preventDefault(); handleRestart(); break;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [playbackSpeed, handlePlayPause, handleSeek, handleRestart, handleSpeedChange]);

  const animationRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (frames.length === 0) return;
    let lastTime = performance.now();

    const animate = (currentTime: number) => {
      if (!isPaused) {
        const deltaTime = (currentTime - lastTime) / 1000;
        framePositionRef.current += deltaTime * playbackSpeed;

        if (framePositionRef.current >= frames.length - 1) {
          framePositionRef.current = frames.length - 1;
          setIsPaused(true);
        }
        if (framePositionRef.current < 0) framePositionRef.current = 0;

        const frameIndex = Math.floor(framePositionRef.current);
        const nextFrameIndex = Math.min(frameIndex + 1, frames.length - 1);
        const t = framePositionRef.current - frameIndex;
        const frame1 = frames[frameIndex];
        const frame2 = frames[nextFrameIndex];

        const interpolatedDrivers: Record<string, DriverPosition> = {};
        for (const code of Object.keys(frame1.drivers)) {
          if (code in frame2.drivers) {
            const p1 = frame1.drivers[code], p2 = frame2.drivers[code];
            interpolatedDrivers[code] = {
              x: lerp(p1.x, p2.x, t), y: lerp(p1.y, p2.y, t),
              dist: lerp(p1.dist, p2.dist, t), lap: p1.lap,
              rel_dist: lerp(p1.rel_dist, p2.rel_dist, t),
              tyre: p1.tyre, position: p1.position,
              speed: lerp(p1.speed, p2.speed, t), gear: p1.gear, drs: p1.drs,
              throttle: lerp(p1.throttle, p2.throttle, t),
              brake: lerp(p1.brake, p2.brake, t),
            };
          } else {
            interpolatedDrivers[code] = frame1.drivers[code];
          }
        }

        setCurrentFrameIndex(frameIndex);
        setInterpolatedFrame({ t: lerp(frame1.t, frame2.t, t), lap: frame1.lap, drivers: interpolatedDrivers, weather: frame1.weather });
        lastTime = currentTime;
      }
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => { if (animationRef.current) cancelAnimationFrame(animationRef.current); };
  }, [frames, isPaused, playbackSpeed]);

  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  const displayFrame = interpolatedFrame || (frames[currentFrameIndex] || null);

  return (
    <div className="race-viewer">
      <div className="race-canvas-column">
        <SessionBanner
          eventName={eventName}
          circuitName={circuitName}
          country={country}
          year={year}
        />
        <div className="canvas-wrapper">
          <AnimatedTrackCanvas
            trackData={trackData}
            frames={frames}
            driverColors={driverColors}
            currentFrame={currentFrameIndex}
            interpolatedFrame={interpolatedFrame}
          />
        </div>
        <div className="playback-controls-area">
          <PlaybackControls
            isPaused={isPaused}
            playbackSpeed={playbackSpeed}
            currentFrame={currentFrameIndex}
            totalFrames={frames.length}
            onPlayPause={handlePlayPause}
            onSpeedChange={handleSpeedChange}
            onSeek={handleSeek}
            onRestart={handleRestart}
            onPrevRace={onPrevRace}
            onNextRace={onNextRace}
            hasPrevRace={hasPrevRace}
            hasNextRace={hasNextRace}
          />
        </div>
      </div>

      <aside className="race-sidebar">
        <Leaderboard
          currentFrame={displayFrame}
          driverColors={driverColors}
          totalLaps={57}
          driverTeams={driverTeams}
        />
      </aside>
    </div>
  );
}
