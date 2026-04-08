import { useState, useCallback } from 'react';
import AnimatedTrackCanvas from '../Track';
import PlaybackControls from '../PlaybackControls';
import Navbar from '../Navbar';
import RaceEventPopup from '../RaceEventPopup';
import DriverSummaryPanel from '../DriverSummaryPanel';
import Leaderboard from '../Leaderboard';
import SessionBanner from '../SessionBanner';
import { useRacePlayback } from '../../../hooks/useRacePlayback';
import { useComparisonMode } from '../../../hooks/useComparisonMode';
import { useTrackStatus } from '../../../hooks/useTrackStatus';
import type { TrackData } from '../../../types/track.types';
import type { Frame, TrackStatus } from '../../../types/api.types';
import './index.css';

interface RaceViewerProps {
  trackData: TrackData;
  frames: Frame[];
  driverColors: Record<string, [number, number, number]>;
  driverTeams: Record<string, string>;
  officialPositions?: Record<string, number>;
  trackStatuses?: TrackStatus[];
  eventName?: string;
  circuitName?: string;
  country?: string;
  year?: number;
  totalLaps?: number;
  onHome: () => void;
  onPrevRace?: () => void;
  onNextRace?: () => void;
  hasPrevRace?: boolean;
  hasNextRace?: boolean;
}

function deriveLeaderCode(
  frame: Frame | null,
  officialPositions: Record<string, number>,
): string | null {
  if (!frame) return null;
  const hasOfficial = Object.keys(officialPositions).length > 0;
  const sorted = Object.entries(frame.drivers)
    .filter(([, d]) => !d.is_out)
    .sort(([codeA, a], [codeB, b]) => {
      if (a.finished && !b.finished) return -1;
      if (!a.finished && b.finished) return 1;
      const posA = hasOfficial ? (officialPositions[codeA] ?? a.position) : a.position;
      const posB = hasOfficial ? (officialPositions[codeB] ?? b.position) : b.position;
      return posA - posB;
    });
  return sorted[0]?.[0] ?? null;
}

export default function RaceViewer({
  trackData, frames, driverColors, driverTeams,
  officialPositions = {},
  trackStatuses = [],
  eventName, circuitName, country, year, totalLaps,
  onHome,
  onPrevRace, onNextRace, hasPrevRace = false, hasNextRace = false,
}: RaceViewerProps) {
  const [focusedDrivers, setFocusedDrivers] = useState<Set<string>>(new Set());

  const {
    currentFrameIndex, interpolatedFrame,
    isPaused, playbackSpeed,
    lapFrameIndices, displayFrame, totalTime,
    handlePlayPause, handleSpeedChange,
    handleSeek, handleSeekToLap, handleRestart: baseHandleRestart,
  } = useRacePlayback(frames, totalLaps);

  const {
    isComparisonMode, comparisonDriver, comparisonPositions,
    setComparisonDriver, toggleComparisonMode, closeComparison,
  } = useComparisonMode(circuitName, currentFrameIndex);

  const { activeEvent, activeStatus, resetStatus } = useTrackStatus(
    displayFrame,
    trackStatuses,
  );

  const handleRestart = useCallback(() => {
    baseHandleRestart();
    resetStatus();
  }, [baseHandleRestart, resetStatus]);

  const handleToggleDriver = useCallback((code: string) => {
    setFocusedDrivers(prev => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  }, []);

  const leaderCode = deriveLeaderCode(displayFrame, officialPositions);

  return (
    <div className="race-viewer">
      <Navbar
        onHome={onHome}
        onToggleComparison={toggleComparisonMode}
        isComparisonMode={isComparisonMode}
      />

      <aside className="race-sidebar">
        {isComparisonMode ? (
          <DriverSummaryPanel
            circuitName={circuitName ?? ''}
            driverCodes={Object.keys(driverColors)}
            driverColors={driverColors}
            driverTeams={driverTeams}
            selectedDriver={comparisonDriver}
            onDriverSelect={setComparisonDriver}
            onClose={closeComparison}
          />
        ) : (
          <Leaderboard
            currentFrame={displayFrame} driverColors={driverColors}
            totalLaps={totalLaps} driverTeams={driverTeams}
            officialPositions={officialPositions}
            focusedDrivers={focusedDrivers}
            onToggleDriver={handleToggleDriver}
          />
        )}
      </aside>

      <div className="race-canvas-column">
        <SessionBanner
          eventName={eventName} circuitName={circuitName}
          country={country} year={isComparisonMode ? undefined : year}
          weather={isComparisonMode ? null : displayFrame?.weather}
        />
        <div
          className="canvas-wrapper"
          style={{ borderColor: !isComparisonMode && activeStatus !== '1' ? (activeEvent?.color ?? '') : '' }}
        >
          <AnimatedTrackCanvas
            trackData={trackData} frames={frames} driverColors={driverColors}
            currentFrame={currentFrameIndex} interpolatedFrame={interpolatedFrame}
            leaderCode={leaderCode} focusedDrivers={focusedDrivers}
            comparisonMode={isComparisonMode}
            comparisonPositions={comparisonPositions}
            comparisonDriverColor={comparisonDriver ? driverColors[comparisonDriver] : undefined}
          />
          <RaceEventPopup event={activeEvent} isActive={!isComparisonMode && activeStatus !== '1'} />
        </div>
        <div className="playback-controls-area">
          <PlaybackControls
            isPaused={isPaused} playbackSpeed={playbackSpeed}
            currentFrame={currentFrameIndex} totalFrames={frames.length}
            totalLaps={totalLaps} lapFrameIndices={lapFrameIndices}
            trackStatuses={isComparisonMode ? [] : trackStatuses} totalTime={totalTime}
            onPlayPause={handlePlayPause} onSpeedChange={handleSpeedChange}
            onSeek={handleSeek} onSeekToLap={handleSeekToLap}
            onRestart={handleRestart}
            onPrevRace={onPrevRace} onNextRace={onNextRace}
            hasPrevRace={hasPrevRace} hasNextRace={hasNextRace}
          />
        </div>
      </div>
    </div>
  );
}
