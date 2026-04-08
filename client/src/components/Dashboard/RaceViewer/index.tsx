import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { supabase } from '../../../lib/supabase';
import AnimatedTrackCanvas from '../Track';
import PlaybackControls from '../PlaybackControls';
import Navbar from '../Navbar';
import RaceEventPopup, { buildRaceEvent } from '../RaceEventPopup';
import DriverSummaryPanel from '../DriverSummaryPanel';
import type { RaceEvent } from '../RaceEventPopup';
import type { TrackData } from '../../../types/track.types';
import type { Frame, DriverPosition, TrackStatus } from '../../../types/api.types';
import './index.css';
import Leaderboard from '../Leaderboard';
import SessionBanner from '../SessionBanner';

const parse = (val: any) => typeof val === 'string' ? JSON.parse(val) : val;
const CHUNK_SIZE = 500;

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

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

type ComparisonPosition = { year: number; x: number; y: number; is_retired: boolean };
type CompSnapshot = Record<string, { x: number; y: number; is_out: boolean }>;

export default function RaceViewer({
  trackData, frames, driverColors, driverTeams,
  officialPositions = {},
  trackStatuses = [],
  eventName, circuitName, country, year, totalLaps,
  onHome,
  onPrevRace, onNextRace, hasPrevRace = false, hasNextRace = false,
}: RaceViewerProps) {
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [interpolatedFrame, setInterpolatedFrame] = useState<Frame | null>(null);
  const [isPaused, setIsPaused]           = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [focusedDrivers, setFocusedDrivers]           = useState<Set<string>>(new Set());
  const [activeEvent, setActiveEvent]                 = useState<RaceEvent | null>(null);
  const [activeStatus, setActiveStatus]               = useState<string>('1');
  const [isComparisonMode, setIsComparisonMode]       = useState(false);
  const [comparisonDriver, setComparisonDriver]       = useState('');
  const [comparisonRaces, setComparisonRaces]         = useState<{ year: number; round: number }[]>([]);
  const [comparisonPositions, setComparisonPositions] = useState<ComparisonPosition[]>([]);
  const [compFetchVersion, setCompFetchVersion]       = useState(0);

  // Cache: `${year}-${chunkIdx}` → per-frame snapshots
  const compCacheRef      = useRef<Map<string, CompSnapshot[]>>(new Map());
  const fetchingChunksRef = useRef<Set<string>>(new Set());
  const framePositionRef  = useRef<number>(0);
  const animationRef      = useRef<number | undefined>(undefined);
  const eventCounterRef   = useRef<number>(0);
  const lastStatusRef     = useRef<string>('1');

  // ── Lap → frame index map ────────────────────────────────────────────────
  const lapFrameIndices = useMemo(() => {
    if (!totalLaps || frames.length === 0) return [];
    const indices: number[] = [];
    for (let lap = 1; lap <= totalLaps; lap++) {
      const idx = frames.findIndex(f => f.lap >= lap);
      indices.push(idx === -1 ? frames.length - 1 : idx);
    }
    return indices;
  }, [frames, totalLaps]);

  // ── Sorted track statuses ────────────────────────────────────────────────
  const sortedStatuses = useMemo(
    () => [...trackStatuses].sort((a, b) => a.start_time - b.start_time),
    [trackStatuses]
  );

  // ── Driver focus ─────────────────────────────────────────────────────────
  const handleToggleDriver = useCallback((code: string) => {
    setFocusedDrivers(prev => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  }, []);

  // ── Playback callbacks ───────────────────────────────────────────────────
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
    lastStatusRef.current = '1';
  }, []);

  // ── Comparison: load race list when driver / mode changes ────────────────
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || !circuitName) {
      setComparisonRaces([]);
      setComparisonPositions([]);
      compCacheRef.current.clear();
      fetchingChunksRef.current.clear();
      return;
    }
    supabase
      .from('races')
      .select('year, round')
      .eq('circuit_name', circuitName)
      .order('year', { ascending: true })
      .then(({ data }) => setComparisonRaces((data ?? []) as { year: number; round: number }[]));
  }, [isComparisonMode, comparisonDriver, circuitName]);

  // ── Comparison: prefetch chunk for current frame (de-duped) ──────────────
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || comparisonRaces.length === 0) return;

    const chunkIdx = Math.floor(currentFrameIndex / CHUNK_SIZE);

    const toFetch = comparisonRaces.filter(race => {
      const key = `${race.year}-${chunkIdx}`;
      return !compCacheRef.current.has(key) && !fetchingChunksRef.current.has(key);
    });

    if (toFetch.length === 0) return;

    toFetch.forEach(race => fetchingChunksRef.current.add(`${race.year}-${chunkIdx}`));

    Promise.all(toFetch.map(async race => {
      const key = `${race.year}-${chunkIdx}`;
      const { data } = await supabase
        .from('race_frames').select('frames')
        .eq('year', race.year).eq('round', race.round).eq('chunk_index', chunkIdx)
        .single();
      fetchingChunksRef.current.delete(key);
      if (!data) return;
      const snapshots: CompSnapshot[] = (parse(data.frames) as Frame[]).map(f =>
        Object.fromEntries(
          Object.entries(f.drivers).map(([code, d]) => [
            code, { x: d.x, y: d.y, is_out: d.is_out === true },
          ])
        )
      );
      compCacheRef.current.set(key, snapshots);
    })).then(() => setCompFetchVersion(v => v + 1));
  }, [currentFrameIndex, comparisonDriver, comparisonRaces, isComparisonMode]);

  // ── Comparison: resolve positions synchronously from cache ────────────────
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || comparisonRaces.length === 0) {
      setComparisonPositions([]);
      return;
    }
    const chunkIdx     = Math.floor(currentFrameIndex / CHUNK_SIZE);
    const frameInChunk = currentFrameIndex % CHUNK_SIZE;
    const positions: ComparisonPosition[] = [];
    for (const race of comparisonRaces) {
      const cached = compCacheRef.current.get(`${race.year}-${chunkIdx}`);
      if (!cached) continue;
      const snap = cached[Math.min(frameInChunk, cached.length - 1)]?.[comparisonDriver];
      if (snap) positions.push({ year: race.year, x: snap.x, y: snap.y, is_retired: snap.is_out });
    }
    setComparisonPositions(positions);
  }, [currentFrameIndex, comparisonDriver, comparisonRaces, isComparisonMode, compFetchVersion]);

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
              x: lerp(p1.x, p2.x, t), y: lerp(p1.y, p2.y, t),
              dist: lerp(p1.dist, p2.dist, t), lap: p1.lap,
              rel_dist: lerp(p1.rel_dist, p2.rel_dist, t),
              tyre: p1.tyre, position: p1.position,
              speed: lerp(p1.speed, p2.speed, t), gear: p1.gear, drs: p1.drs,
              throttle: lerp(p1.throttle, p2.throttle, t),
              brake: lerp(p1.brake, p2.brake, t),
              is_out: p1.is_out, finished: p1.finished,
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

  // ── Derived display values ───────────────────────────────────────────────
  const displayFrame = interpolatedFrame || frames[currentFrameIndex] || null;
  const leaderCode   = deriveLeaderCode(displayFrame, officialPositions);
  const totalTime    = frames[frames.length - 1]?.t ?? 0;

  // ── Track status event detection ─────────────────────────────────────────
  useEffect(() => {
    if (!displayFrame || sortedStatuses.length === 0) return;
    const t = displayFrame.t;

    let status = '1';
    for (const s of sortedStatuses) {
      if (s.start_time <= t) status = s.status;
      else break;
    }

    if (status !== lastStatusRef.current) {
      lastStatusRef.current = status;
      setActiveStatus(status);
      const event = buildRaceEvent(status, ++eventCounterRef.current);
      if (event) setActiveEvent(event);
    }
  }, [displayFrame?.t, sortedStatuses]);

  return (
    <div className="race-viewer">
      <Navbar
        onHome={onHome}
        onToggleComparison={() => setIsComparisonMode(p => !p)}
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
            onClose={() => { setIsComparisonMode(false); setComparisonDriver(''); }}
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
