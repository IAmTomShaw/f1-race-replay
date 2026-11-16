"use client";

import React, { useEffect } from "react";
import { AlertTriangle, ListOrdered, RotateCcw } from "lucide-react";
import { useReplayStore } from "@/store/useReplayStore";
import { TopSessionHeader } from "@/components/TopSessionHeader";
import { TelemetryInspector } from "@/components/TelemetryInspector";
import { TrackCanvas } from "@/components/TrackCanvas";
import { StartLightsGantry } from "@/components/StartLightsGantry";
import { LeaderboardPanel } from "@/components/LeaderboardPanel";
import { TimelineControls } from "@/components/TimelineControls";
import { SessionPickerModal } from "@/components/SessionPickerModal";
import { OverlayModals } from "@/components/OverlayModals";

export default function PitWallPage() {
  const isLoading = useReplayStore((s) => s.isLoading);
  const loadingProgress = useReplayStore((s) => s.loadingProgress);
  const loadingMessage = useReplayStore((s) => s.loadingMessage);
  const errorMessage = useReplayStore((s) => s.errorMessage);
  const showLeaderboard = useReplayStore((s) => s.showLeaderboard);
  const toggleLeaderboard = useReplayStore((s) => s.toggleLeaderboard);
  const restoreInitialSession = useReplayStore((s) => s.restoreInitialSession);
  const loadDemo = useReplayStore((s) => s.loadDemo);

  useEffect(() => {
    restoreInitialSession();
  }, [restoreInitialSession]);

  // Global Pit Wall Keyboard Shortcuts (matches desktop controls)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      const store = useReplayStore.getState();
      switch (e.key) {
        case " ":
          e.preventDefault();
          store.togglePlay();
          break;
        case "ArrowLeft":
          e.preventDefault();
          store.skipBy(-10);
          break;
        case "ArrowRight":
          e.preventDefault();
          store.skipBy(10);
          break;
        case "ArrowUp":
          e.preventDefault();
          store.stepPlaybackSpeed(1);
          break;
        case "ArrowDown":
          e.preventDefault();
          store.stepPlaybackSpeed(-1);
          break;
        case "1":
          store.setPlaybackSpeed(0.5);
          break;
        case "2":
          store.setPlaybackSpeed(1);
          break;
        case "3":
          store.setPlaybackSpeed(2);
          break;
        case "4":
          store.setPlaybackSpeed(4);
          break;
        case "r":
        case "R":
          store.restart();
          break;
        case "d":
        case "D":
          store.toggleDrsZones();
          break;
        case "l":
        case "L":
          store.toggleDriverLabels();
          break;
        case "t":
        case "T":
          store.toggleLeaderboard();
          break;
        case "b":
        case "B":
          store.toggleProgressBar();
          break;
        case "i":
        case "I":
          store.toggleSessionBanner();
          break;
        case "c":
        case "C":
          store.setActiveOverlay("drivers_champ");
          break;
        case "a":
        case "A":
          store.setActiveOverlay("constructors_champ");
          break;
        case "h":
        case "H":
          store.setActiveOverlay("controls_help");
          break;
        case "Escape":
          store.setActiveOverlay("none");
          break;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <main className="pitwall-backdrop flex h-screen w-screen flex-col overflow-hidden">
      <TopSessionHeader />

      {/* Main 3-Pane Pit Wall Console */}
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        {/* Left Pane: Car Telemetry & FIA Race Control */}
        <div className="hidden min-h-0 shrink-0 lg:flex">
          <TelemetryInspector />
        </div>

        {/* Center Pane: 60 FPS Circuit Map */}
        <div className="relative min-h-[240px] min-w-0 flex-1 overflow-hidden">
          <TrackCanvas />
          <StartLightsGantry />

          {/* On-screen Leaderboard Toggle Pill when hidden (or quick toggle) */}
          <button
            onClick={toggleLeaderboard}
            title="Toggle Timing Leaderboard (T)"
            className={`absolute top-3 right-3 z-20 flex h-7 cursor-pointer items-center gap-1.5 rounded border px-2.5 font-mono text-[10px] font-semibold uppercase backdrop-blur-md transition ${
              showLeaderboard
                ? "border-white/15 bg-[#0B0E15]/80 text-slate-300 hover:border-white/30 hover:text-white"
                : "border-[#E10600]/60 bg-[#E10600]/20 text-white hover:bg-[#E10600]/35"
            }`}
          >
            <ListOrdered className="h-3.5 w-3.5" />
            {showLeaderboard ? "Hide Timing" : "Show Timing"}
            <span className="rounded bg-white/10 px-1 py-0.5 text-[9px] text-slate-300">
              T
            </span>
          </button>

          {/* Loading / FastF1 Build Progress Overlay */}
          {isLoading && (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#07090E]/85 backdrop-blur-sm">
              <div className="w-full max-w-md rounded-lg border border-white/12 bg-[#0E121B] p-6 shadow-2xl">
                <div className="flex items-center justify-between">
                  <span className="font-display text-sm font-bold tracking-wider text-white uppercase">
                    Telemetry Link
                  </span>
                  <span className="font-mono text-xs font-bold text-[#E10600] tabular-nums">
                    {loadingProgress}%
                  </span>
                </div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-[#E10600] transition-all duration-300"
                    style={{ width: `${loadingProgress}%` }}
                  />
                </div>
                <p className="mt-3 font-mono text-xs text-slate-300">
                  {loadingMessage}
                </p>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && !isLoading && (
            <div className="absolute inset-x-6 top-6 z-30 mx-auto max-w-lg rounded-lg border border-red-500/40 bg-[#170C10]/95 p-4 shadow-xl">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
                <div className="flex-1">
                  <div className="font-display text-sm font-bold text-red-200">
                    Telemetry Load Error
                  </div>
                  <p className="mt-1 font-mono text-xs text-red-300/90">
                    {errorMessage}
                  </p>
                  <button
                    onClick={() => loadDemo()}
                    className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded bg-white/10 px-3 py-1 font-mono text-xs font-semibold text-white hover:bg-white/20"
                  >
                    <RotateCcw className="h-3.5 w-3.5" /> Return to Demo Race
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Pane: 20-Driver Timing Tower */}
        {showLeaderboard && (
          <div className="flex h-[38vh] min-h-0 w-full shrink-0 md:h-full md:w-[272px] lg:w-[292px]">
            <LeaderboardPanel />
          </div>
        )}
      </div>

      {/* Bottom Scrubber & Transport Controls */}
      <TimelineControls />

      {/* Modals & Championship Overlays */}
      <SessionPickerModal />
      <OverlayModals />
    </main>
  );
}
