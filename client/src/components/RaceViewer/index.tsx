import { useState, useEffect, useRef, useCallback } from 'react';
import AnimatedTrackCanvas from '../Track';
import PlaybackControls from '../PlaybackControls';
import type { TrackData } from '../../types/track.types';
import type { Frame, DriverPosition } from '../../types/api.types';
import './index.css';
import Leaderboard from '../Leaderboard';

interface RaceViewerProps {
  trackData: TrackData;
  frames: Frame[];
  driverColors: Record<string, [number, number, number]>;
}

export default function RaceViewer({ trackData, frames, driverColors }: RaceViewerProps) {
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [interpolatedFrame, setInterpolatedFrame] = useState<Frame | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(0.5);

  // Use float for sub-frame precision
  const framePositionRef = useRef<number>(0);

  // Playback control handlers
  const handlePlayPause = useCallback(() => {
    setIsPaused(prev => !prev);
  }, []);

  const handleSpeedChange = useCallback((speed: number) => {
    setPlaybackSpeed(speed);
  }, []);

  const handleSeek = useCallback((frame: number) => {
    framePositionRef.current = Math.max(0, Math.min(frame, frames.length - 1));
    setCurrentFrameIndex(Math.floor(framePositionRef.current));
  }, [frames]);

  const handleRestart = useCallback(() => {
    framePositionRef.current = 0;
    setCurrentFrameIndex(0);
    setIsPaused(true);
  }, []);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case ' ':
          e.preventDefault();
          handlePlayPause();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          handleSeek(Math.floor(framePositionRef.current) - 25);
          break;
        case 'ArrowRight':
          e.preventDefault();
          handleSeek(Math.floor(framePositionRef.current) + 25);
          break;
        case 'ArrowUp':
          e.preventDefault();
          handleSpeedChange(Math.min(8, playbackSpeed * 2));
          break;
        case 'ArrowDown':
          e.preventDefault();
          handleSpeedChange(Math.max(0.1, playbackSpeed / 2));
          break;
        case 'r':
        case 'R':
          e.preventDefault();
          handleRestart();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [playbackSpeed, handlePlayPause, handleSeek, handleRestart, handleSpeedChange]);

  // Animation loop with interpolation
  const animationRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (frames.length === 0) return;

    let lastTime = performance.now();

    const animate = (currentTime: number) => {
      if (!isPaused) {
        const deltaTime = (currentTime - lastTime) / 1000; // Delta in seconds
        
        // At 1x speed: advance 1 data frame per second (since data is 25 FPS)
        // At 0.5x speed: advance 0.5 frames per second
        // The key insight: we have 25 frames of data per 1 second of real race time
        const framesPerSecond = 1 * playbackSpeed; // Real-time = 1 frame per second
        
        // Advance frame position
        framePositionRef.current += deltaTime * framesPerSecond;
        
        // Clamp to valid range
        if (framePositionRef.current >= frames.length - 1) {
          framePositionRef.current = frames.length - 1;
          setIsPaused(true);
        }
        
        if (framePositionRef.current < 0) {
          framePositionRef.current = 0;
        }
        
        // Get integer frame indices
        const frameIndex = Math.floor(framePositionRef.current);
        const nextFrameIndex = Math.min(frameIndex + 1, frames.length - 1);
        
        // Calculate interpolation factor (0.0 to 1.0)
        const t = framePositionRef.current - frameIndex;
        
        // Interpolate between current and next frame
        const frame1 = frames[frameIndex];
        const frame2 = frames[nextFrameIndex];
        
        // Create interpolated frame
        const interpolatedDrivers: Record<string, DriverPosition> = {};
        
        for (const code of Object.keys(frame1.drivers)) {
          if (code in frame2.drivers) {
            const pos1 = frame1.drivers[code];
            const pos2 = frame2.drivers[code];
            
            interpolatedDrivers[code] = {
              x: lerp(pos1.x, pos2.x, t),
              y: lerp(pos1.y, pos2.y, t),
              dist: lerp(pos1.dist, pos2.dist, t),
              lap: pos1.lap,
              rel_dist: lerp(pos1.rel_dist, pos2.rel_dist, t),
              tyre: pos1.tyre,
              position: pos1.position,
              speed: lerp(pos1.speed, pos2.speed, t),
              gear: pos1.gear,
              drs: pos1.drs,
              throttle: lerp(pos1.throttle, pos2.throttle, t),
              brake: lerp(pos1.brake, pos2.brake, t),
            };
          } else {
            interpolatedDrivers[code] = frame1.drivers[code];
          }
        }
        
        const newFrame: Frame = {
          t: lerp(frame1.t, frame2.t, t),
          lap: frame1.lap,
          drivers: interpolatedDrivers,
          weather: frame1.weather,
        };
        
        setCurrentFrameIndex(frameIndex);
        setInterpolatedFrame(newFrame);
        
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
  }, [frames, isPaused, playbackSpeed]);

  // Helper function
  const lerp = (a: number, b: number, t: number): number => {
    return a + (b - a) * t;
  };

  // Use interpolated frame if available, otherwise use current frame
  const displayFrame = interpolatedFrame || (frames[currentFrameIndex] || null);

  return (
    <div className="race-viewer">
      {/* Left: Canvas + Controls */}
      <div className="race-canvas-column">
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
          />
        </div>
      </div>

      {/* Right: Sidebar */}
      <aside className="race-sidebar">
        <Leaderboard
          currentFrame={displayFrame}
          driverColors={driverColors}
          totalLaps={57}
        />
      </aside>
    </div>
  );
}
