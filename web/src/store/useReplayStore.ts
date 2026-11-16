import { create } from "zustand";
import {
  ColumnarFrames,
  InterpolatedSnapshot,
  ReplayManifest,
} from "@/types/replay";
import {
  checkBackendHealth,
  fetchDemoBundle,
  fetchSessionBundle,
  pollSessionStatus,
  prepareSessionBundle,
} from "@/lib/api";
import { detectLaunchTimeS, sampleSnapshotAtTime } from "@/lib/interpolation";

export const PLAYBACK_SPEEDS = [
  0.1, 0.2, 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256,
] as const;

export type OverlayPanel =
  | "none"
  | "session_picker"
  | "drivers_champ"
  | "constructors_champ"
  | "controls_help";

interface ReplayState {
  manifest: ReplayManifest | null;
  frames: ColumnarFrames | null;
  snapshot: InterpolatedSnapshot | null;

  // High-frequency clock read directly by Canvas 60fps loop
  currentTimeS: number;
  durationS: number;
  launchTimeS: number;
  preRollS: number;
  preRollElapsedS: number;
  isPlaying: boolean;
  playbackSpeed: number;

  // Selection & HUD options
  selectedDrivers: string[];
  gapMode: "leader" | "interval";
  showDrsZones: boolean;
  showDriverLabels: boolean;
  showLeaderboard: boolean;
  showProgressBar: boolean;
  showSessionBanner: boolean;
  activeOverlay: OverlayPanel;

  // Connection & loading status
  backendOnline: boolean;
  isLoading: boolean;
  loadingProgress: number;
  loadingMessage: string;
  errorMessage: string | null;

  // Actions
  restoreInitialSession: () => Promise<void>;
  loadDemo: () => Promise<void>;
  loadFastF1Session: (
    year: number,
    round: number,
    sessionType: string
  ) => Promise<void>;
  refreshBackendStatus: () => Promise<void>;

  setPlaying: (playing: boolean) => void;
  togglePlay: () => void;
  seekTo: (timeS: number, syncUi?: boolean) => void;
  skipBy: (deltaS: number) => void;
  restart: () => void;
  setPlaybackSpeed: (speed: number) => void;
  stepPlaybackSpeed: (direction: 1 | -1) => void;

  // Called by the RAF loop: advances time smoothly; updates React snapshot at ~12Hz
  advanceClock: (dtRealSeconds: number, forceUiSync?: boolean) => void;

  selectDriver: (code: string, multi?: boolean) => void;
  clearSelectedDrivers: () => void;
  toggleGapMode: () => void;
  toggleDrsZones: () => void;
  toggleDriverLabels: () => void;
  toggleLeaderboard: () => void;
  toggleProgressBar: () => void;
  toggleSessionBanner: () => void;
  setActiveOverlay: (panel: OverlayPanel) => void;
}

let lastUiSyncWallMs = 0;

const LAST_SESSION_STORAGE_KEY = "f1_replay_last_session";

type StoredSessionRef =
  | { type: "demo" }
  | { type: "session"; year: number; round: number; sessionType: string };

function persistSessionSelection(ref: StoredSessionRef) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LAST_SESSION_STORAGE_KEY, JSON.stringify(ref));
  } catch {
    // Ignore storage quota/privacy mode errors
  }

  try {
    const url = new URL(window.location.href);
    if (ref.type === "session") {
      url.searchParams.set("year", String(ref.year));
      url.searchParams.set("round", String(ref.round));
      url.searchParams.set("session", ref.sessionType.toUpperCase());
    } else {
      url.searchParams.delete("year");
      url.searchParams.delete("round");
      url.searchParams.delete("session");
    }
    window.history.replaceState(null, "", url.pathname + url.search);
  } catch {
    // Ignore history API errors
  }
}

function readPersistedSession(): StoredSessionRef {
  if (typeof window === "undefined") return { type: "demo" };
  try {
    const params = new URLSearchParams(window.location.search);
    const yStr = params.get("year");
    const rStr = params.get("round");
    const sStr = params.get("session");
    if (yStr && rStr) {
      const year = Number.parseInt(yStr, 10);
      const round = Number.parseInt(rStr, 10);
      const sessionType = (sStr || "R").toUpperCase();
      if (
        Number.isFinite(year) &&
        Number.isFinite(round) &&
        round >= 1 &&
        (sessionType === "R" || sessionType === "S")
      ) {
        return { type: "session", year, round, sessionType };
      }
    }
  } catch {
    // Fall through to localStorage
  }

  try {
    const raw = window.localStorage.getItem(LAST_SESSION_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredSessionRef>;
      if (
        parsed.type === "session" &&
        typeof parsed.year === "number" &&
        typeof parsed.round === "number" &&
        (parsed.sessionType === "R" || parsed.sessionType === "S")
      ) {
        return {
          type: "session",
          year: parsed.year,
          round: parsed.round,
          sessionType: parsed.sessionType,
        };
      }
    }
  } catch {
    // Ignore storage errors
  }

  return { type: "demo" };
}

export const useReplayStore = create<ReplayState>((set, get) => ({
  manifest: null,
  frames: null,
  snapshot: null,

  currentTimeS: 0,
  durationS: 0,
  launchTimeS: 0,
  preRollS: 0,
  preRollElapsedS: 0,
  isPlaying: false,
  playbackSpeed: 1,

  selectedDrivers: ["VER", "NOR"],
  gapMode: "leader",
  showDrsZones: true,
  showDriverLabels: true,
  showLeaderboard: true,
  showProgressBar: true,
  showSessionBanner: true,
  activeOverlay: "none",

  backendOnline: false,
  isLoading: true,
  loadingProgress: 10,
  loadingMessage: "Initializing Pit Wall Telemetry...",
  errorMessage: null,

  refreshBackendStatus: async () => {
    const online = await checkBackendHealth();
    set({ backendOnline: online });
  },

  restoreInitialSession: async () => {
    const saved = readPersistedSession();
    if (saved.type === "session") {
      const online = await checkBackendHealth();
      if (online) {
        await get().loadFastF1Session(
          saved.year,
          saved.round,
          saved.sessionType
        );
        return;
      }
    }
    await get().loadDemo();
  },

  loadDemo: async () => {
    persistSessionSelection({ type: "demo" });
    set({
      isLoading: true,
      loadingProgress: 25,
      loadingMessage: "Loading 20-driver Grand Prix Showcase...",
      errorMessage: null,
    });
    try {
      const [{ manifest, frames, source }, online] = await Promise.all([
        fetchDemoBundle(),
        checkBackendHealth(),
      ]);
      const initialSnap = sampleSnapshotAtTime(manifest, frames, 0);
      const launchTimeS = detectLaunchTimeS(frames);
      const preRollS = Math.max(0, 6.0 - launchTimeS);
      const topTwo = initialSnap.driversSorted.slice(0, 2).map((d) => d.code);
      set({
        manifest,
        frames,
        snapshot: initialSnap,
        currentTimeS: 0,
        durationS: manifest.session_info.duration_s,
        launchTimeS,
        preRollS,
        preRollElapsedS: 0,
        isPlaying: false,
        selectedDrivers: topTwo,
        backendOnline: online || source === "api",
        isLoading: false,
        loadingProgress: 100,
        loadingMessage: "Ready",
        activeOverlay: "none",
      });
    } catch (err) {
      set({
        isLoading: false,
        errorMessage: err instanceof Error ? err.message : "Failed to load demo",
      });
    }
  },

  loadFastF1Session: async (year, round, sessionType) => {
    set({
      activeOverlay: "none",
      isLoading: true,
      isPlaying: false,
      loadingProgress: 5,
      loadingMessage: `Preparing ${year} Round ${round} (${sessionType === "S" ? "Sprint" : "Race"})...`,
      errorMessage: null,
    });

    try {
      let status = await prepareSessionBundle(year, round, sessionType);
      let consecutivePollErrors = 0;
      while (status.status === "building") {
        set({
          loadingProgress: Math.max(8, status.progress),
          loadingMessage: status.message || "Processing telemetry...",
        });
        await new Promise((r) => setTimeout(r, 1200));
        try {
          status = await pollSessionStatus(year, round, sessionType);
          consecutivePollErrors = 0;
        } catch (pollErr) {
          consecutivePollErrors += 1;
          if (consecutivePollErrors >= 5) {
            throw pollErr;
          }
        }
      }

      if (status.status === "error") {
        throw new Error(status.message || "Session telemetry build failed.");
      }

      set({
        loadingProgress: 94,
        loadingMessage: "Downloading compressed telemetry frames...",
      });

      const { manifest, frames } = await fetchSessionBundle(
        year,
        round,
        sessionType
      );
      const initialSnap = sampleSnapshotAtTime(manifest, frames, 0);
      const launchTimeS = detectLaunchTimeS(frames);
      const preRollS = Math.max(0, 6.0 - launchTimeS);
      const topTwo = initialSnap.driversSorted.slice(0, 2).map((d) => d.code);

      persistSessionSelection({
        type: "session",
        year,
        round,
        sessionType: sessionType.toUpperCase(),
      });

      set({
        manifest,
        frames,
        snapshot: initialSnap,
        currentTimeS: 0,
        durationS: manifest.session_info.duration_s,
        launchTimeS,
        preRollS,
        preRollElapsedS: 0,
        isPlaying: false,
        selectedDrivers: topTwo,
        backendOnline: true,
        isLoading: false,
        loadingProgress: 100,
        loadingMessage: "Ready",
        activeOverlay: "none",
      });
    } catch (err) {
      set({
        isLoading: false,
        errorMessage:
          err instanceof Error ? err.message : "Failed to load FastF1 session",
      });
    }
  },

  setPlaying: (playing) => set({ isPlaying: playing }),
  togglePlay: () => {
    const state = get();
    if (!state.manifest || !state.frames) return;
    if (!state.isPlaying && state.currentTimeS >= state.durationS) {
      const snap = sampleSnapshotAtTime(state.manifest, state.frames, 0);
      set({ currentTimeS: 0, snapshot: snap, isPlaying: true });
      return;
    }
    set({ isPlaying: !state.isPlaying });
  },

  seekTo: (timeS, syncUi = true) => {
    const { manifest, frames, durationS, preRollS } = get();
    if (!manifest || !frames) return;
    const clamped = Math.max(0, Math.min(durationS, timeS));
    const nextPreRollElapsed = clamped === 0 ? 0 : preRollS;
    if (syncUi) {
      const snap = sampleSnapshotAtTime(manifest, frames, clamped);
      set({
        currentTimeS: clamped,
        preRollElapsedS: nextPreRollElapsed,
        snapshot: snap,
      });
    } else {
      set({ currentTimeS: clamped, preRollElapsedS: nextPreRollElapsed });
    }
  },

  skipBy: (deltaS) => {
    const { currentTimeS, seekTo } = get();
    seekTo(currentTimeS + deltaS, true);
  },

  restart: () => {
    const { manifest, frames } = get();
    if (!manifest || !frames) return;
    const snap = sampleSnapshotAtTime(manifest, frames, 0);
    set({
      currentTimeS: 0,
      preRollElapsedS: 0,
      snapshot: snap,
      isPlaying: false,
    });
  },

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  stepPlaybackSpeed: (direction) => {
    const { playbackSpeed } = get();
    const curIdx = PLAYBACK_SPEEDS.findIndex((s) => s >= playbackSpeed);
    const baseIdx = curIdx === -1 ? 3 : curIdx;
    const nextIdx = Math.max(
      0,
      Math.min(PLAYBACK_SPEEDS.length - 1, baseIdx + direction)
    );
    set({ playbackSpeed: PLAYBACK_SPEEDS[nextIdx] });
  },

  advanceClock: (dtRealSeconds, forceUiSync = false) => {
    const state = get();
    if (!state.manifest || !state.frames || !state.isPlaying) return;

    const deltaSim = dtRealSeconds * state.playbackSpeed;
    let nextPreRollElapsed = state.preRollElapsedS;
    let nextTime = state.currentTimeS;

    if (nextPreRollElapsed < state.preRollS) {
      const remainingPreRoll = state.preRollS - nextPreRollElapsed;
      if (deltaSim <= remainingPreRoll) {
        nextPreRollElapsed += deltaSim;
      } else {
        nextPreRollElapsed = state.preRollS;
        nextTime = Math.min(state.durationS, nextTime + (deltaSim - remainingPreRoll));
      }
    } else {
      nextTime = Math.min(state.durationS, state.currentTimeS + deltaSim);
    }

    const reachedEnd = nextTime >= state.durationS;

    const nowMs = performance.now();
    // Throttle React HUD state updates to ~12 Hz while Canvas reads currentTimeS at 60 FPS
    if (forceUiSync || reachedEnd || nowMs - lastUiSyncWallMs >= 80) {
      lastUiSyncWallMs = nowMs;
      const snap = sampleSnapshotAtTime(state.manifest, state.frames, nextTime);
      set({
        currentTimeS: nextTime,
        preRollElapsedS: nextPreRollElapsed,
        snapshot: snap,
        isPlaying: reachedEnd ? false : state.isPlaying,
      });
    } else {
      state.currentTimeS = nextTime;
      state.preRollElapsedS = nextPreRollElapsed;
    }
  },

  selectDriver: (code, multi = false) =>
    set((state) => {
      if (multi) {
        const exists = state.selectedDrivers.includes(code);
        return {
          selectedDrivers: exists
            ? state.selectedDrivers.filter((c) => c !== code)
            : [...state.selectedDrivers.slice(-3), code],
        };
      }
      if (
        state.selectedDrivers.length === 1 &&
        state.selectedDrivers[0] === code
      ) {
        return { selectedDrivers: [] };
      }
      return { selectedDrivers: [code] };
    }),

  clearSelectedDrivers: () => set({ selectedDrivers: [] }),

  toggleGapMode: () =>
    set((s) => ({ gapMode: s.gapMode === "leader" ? "interval" : "leader" })),
  toggleDrsZones: () => set((s) => ({ showDrsZones: !s.showDrsZones })),
  toggleDriverLabels: () =>
    set((s) => ({ showDriverLabels: !s.showDriverLabels })),
  toggleLeaderboard: () =>
    set((s) => ({ showLeaderboard: !s.showLeaderboard })),
  toggleProgressBar: () =>
    set((s) => ({ showProgressBar: !s.showProgressBar })),
  toggleSessionBanner: () =>
    set((s) => ({ showSessionBanner: !s.showSessionBanner })),
  setActiveOverlay: (panel) =>
    set((s) => ({
      activeOverlay: s.activeOverlay === panel ? "none" : panel,
    })),
}));
