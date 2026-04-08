import { useState, useRef, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import type { Frame } from '../types/api.types';

const parse = (val: unknown) => typeof val === 'string' ? JSON.parse(val) : val;
const CHUNK_SIZE = 500;

type ComparisonPosition = { year: number; x: number; y: number; is_retired: boolean };
type CompSnapshot       = Record<string, { x: number; y: number; is_out: boolean }>;

export function useComparisonMode(circuitName: string | undefined, currentFrameIndex: number) {
  const [isComparisonMode, setIsComparisonMode]       = useState(false);
  const [comparisonDriver, setComparisonDriver]       = useState('');
  const [comparisonRaces, setComparisonRaces]         = useState<{ year: number; round: number }[]>([]);
  const [comparisonPositions, setComparisonPositions] = useState<ComparisonPosition[]>([]);
  const [compFetchVersion, setCompFetchVersion]       = useState(0);

  const compCacheRef      = useRef<Map<string, CompSnapshot[]>>(new Map());
  const fetchingChunksRef = useRef<Set<string>>(new Set());

  // ── Load race list when driver / mode changes ────────────────────────────
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

  // ── Prefetch chunk for current frame (de-duped) ──────────────────────────
  useEffect(() => {
    if (!isComparisonMode || !comparisonDriver || comparisonRaces.length === 0) return;

    const chunkIdx = Math.floor(currentFrameIndex / CHUNK_SIZE);

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

  // ── Resolve positions from cache ─────────────────────────────────────────
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

  const toggleComparisonMode = () => setIsComparisonMode(p => !p);
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
