import { useState, useRef, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import type { Frame } from '../types/api.types';

/**
 * Parses a value that may arrive from Supabase as either a JSON string or a
 * pre-parsed object. Supabase occasionally returns JSONB columns as raw strings
 * depending on the client version and column type.
 *
 * @param {unknown} val - The value to parse.
 * @returns {unknown} The parsed object, or the original value if it was not a string.
 */
const parse = (val: unknown) => typeof val === 'string' ? JSON.parse(val) : val;

/**
 * Number of telemetry frames fetched and cached per database request.
 * Frames are grouped into fixed-size chunks so only the data needed for the
 * current playback window is loaded, rather than the full race at once.
 */
const CHUNK_SIZE = 500;

/** A single historical position entry for the selected comparison driver. */
type ComparisonPosition = { year: number; x: number; y: number; is_retired: boolean };

/**
 * A lightweight per-driver snapshot extracted from a full telemetry frame.
 * Keyed by driver code, containing only the fields needed for canvas rendering.
 */
type CompSnapshot = Record<string, { x: number; y: number; is_out: boolean }>;

/**
 * Manages the driver comparison overlay mode. When active, this hook fetches
 * historical telemetry for a selected driver across all available years at the
 * current circuit and exposes per-year dot positions synced to the current
 * playback frame index.
 *
 * Data is fetched in `CHUNK_SIZE`-frame pages from Supabase and stored in a
 * ref-based cache so chunks are only requested once per session.
 *
 * @param {string | undefined} circuitName - Name of the current circuit; used to
 *   query which historical races are available for comparison.
 * @param {number} currentFrameIndex - The current playback frame index, used to
 *   determine which chunk to prefetch and which snapshot to display.
 *
 * @returns {{
 *   isComparisonMode: boolean,
 *   comparisonDriver: string,
 *   comparisonPositions: ComparisonPosition[],
 *   setComparisonDriver: (driver: string) => void,
 *   toggleComparisonMode: () => void,
 *   closeComparison: () => void,
 * }} Comparison state and control callbacks for the consumer component.
 */
export function useComparisonMode(circuitName: string | undefined, currentFrameIndex: number) {
  const [isComparisonMode, setIsComparisonMode] = useState(false);
  const [comparisonDriver, setComparisonDriver] = useState('');
  const [comparisonRaces, setComparisonRaces]   = useState<{ year: number; round: number }[]>([]);
  const [comparisonPositions, setComparisonPositions] = useState<ComparisonPosition[]>([]);
  const [compFetchVersion, setCompFetchVersion] = useState(0);

  const compCacheRef = useRef<Map<string, CompSnapshot[]>>(new Map());
  const fetchingChunksRef = useRef<Set<string>>(new Set());

  /**
   * Fetches the list of races at the current circuit whenever the selected driver
   * or comparison mode changes. Also clears the cache and any in-flight fetch
   * markers when the mode is deactivated or the driver is cleared.
   */
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || !circuitName) {
      setComparisonRaces([]);
      setComparisonPositions([]);
      compCacheRef.current.clear();
      fetchingChunksRef.current.clear();
      return;
    }
    void supabase
      .from('races')
      .select('year, round')
      .eq('circuit_name', circuitName)
      .order('year', { ascending: true })
      .then(({ data }) => setComparisonRaces((data ?? []) as { year: number; round: number }[]));
  }, [isComparisonMode, comparisonDriver, circuitName]);

  /**
   * When the playback position advances into a new chunk window, fetches the
   * corresponding `race_frames` rows for all known comparison races that aren't
   * already cached or in flight.
   *
   * Each fetched chunk is stored in `compCacheRef` and `compFetchVersion` is
   * bumped so the position-derivation effect below can re-run.
   */
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || comparisonRaces.length === 0) return;

    const chunkIdx = Math.floor(currentFrameIndex / CHUNK_SIZE);

    /** Only request races whose chunk is neither cached nor currently being fetched. */
    const toFetch = comparisonRaces.filter(race => {
      const key = `${race.year}-${chunkIdx}`;
      return !compCacheRef.current.has(key) && !fetchingChunksRef.current.has(key);
    });

    if (toFetch.length === 0) return;

    toFetch.forEach(race => fetchingChunksRef.current.add(`${race.year}-${chunkIdx}`));

    void Promise.all(toFetch.map(async race => {
      const key = `${race.year}-${chunkIdx}`;
      const { data } = await supabase
        .from('race_frames').select('frames')
        .eq('year', race.year).eq('round', race.round).eq('chunk_index', chunkIdx)
        .single();

      fetchingChunksRef.current.delete(key);
      if (!data) return;

      /**
       * Flatten each full telemetry frame into a lightweight snapshot containing
       * only the x/y position and retirement status per driver.
       */
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

  /**
   * On every frame advance (or after a new chunk loads), reads the cached snapshot
   * for each historical race and builds the `comparisonPositions` array consumed
   * by the canvas. Races whose chunk isn't cached yet are silently skipped.
   *
   * The frame index within a chunk is clamped to the last available snapshot so
   * the final position is held if the historical race ended before the current
   * playback frame.
   */
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

  /** Toggles comparison mode on or off without clearing the selected driver. */
  const toggleComparisonMode = () => setIsComparisonMode(p => !p);
  /** Exits comparison mode and resets the selected driver, clearing all cached data via the first effect. */
  const closeComparison      = () => { setIsComparisonMode(false); setComparisonDriver(''); };

  return {
    isComparisonMode,
    comparisonDriver,
    comparisonPositions,
    setComparisonDriver,
    toggleComparisonMode,
    closeComparison,
  };
}
