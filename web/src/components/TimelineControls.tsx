"use client";

import React, { useRef, useState } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  Rewind,
  FastForward,
  Trophy,
  Award,
  HelpCircle,
  Tag,
  Zap,
  ListOrdered,
} from "lucide-react";
import { PLAYBACK_SPEEDS, useReplayStore } from "@/store/useReplayStore";
import { formatRaceClock } from "@/lib/interpolation";

export const TimelineControls: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const currentTimeS = useReplayStore((s) => s.currentTimeS);
  const durationS = useReplayStore((s) => s.durationS);
  const isPlaying = useReplayStore((s) => s.isPlaying);
  const playbackSpeed = useReplayStore((s) => s.playbackSpeed);
  const showProgressBar = useReplayStore((s) => s.showProgressBar);
  const showDrsZones = useReplayStore((s) => s.showDrsZones);
  const showDriverLabels = useReplayStore((s) => s.showDriverLabels);
  const showLeaderboard = useReplayStore((s) => s.showLeaderboard);
  const activeOverlay = useReplayStore((s) => s.activeOverlay);

  const togglePlay = useReplayStore((s) => s.togglePlay);
  const seekTo = useReplayStore((s) => s.seekTo);
  const skipBy = useReplayStore((s) => s.skipBy);
  const restart = useReplayStore((s) => s.restart);
  const setPlaybackSpeed = useReplayStore((s) => s.setPlaybackSpeed);
  const toggleDrsZones = useReplayStore((s) => s.toggleDrsZones);
  const toggleDriverLabels = useReplayStore((s) => s.toggleDriverLabels);
  const toggleLeaderboard = useReplayStore((s) => s.toggleLeaderboard);
  const setActiveOverlay = useReplayStore((s) => s.setActiveOverlay);

  const trackRef = useRef<HTMLDivElement>(null);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [hoverX, setHoverX] = useState<number>(0);

  if (!manifest) return null;

  const progressPct =
    durationS > 0 ? Math.min(100, Math.max(0, (currentTimeS / durationS) * 100)) : 0;

  const computeTimeFromPointer = (clientX: number): number => {
    const el = trackRef.current;
    if (!el || durationS <= 0) return 0;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return ratio * durationS;
  };

  return (
    <footer className="border-t border-white/8 bg-[#0A0D13]/95 px-4 py-2.5 backdrop-blur-md">
      {/* Event-Annotated Timeline Scrubber */}
      {showProgressBar && (
        <div className="mb-2.5">
          <div
            ref={trackRef}
            onClick={(e) => seekTo(computeTimeFromPointer(e.clientX), true)}
            onMouseMove={(e) => {
              const el = trackRef.current;
              if (!el) return;
              const rect = el.getBoundingClientRect();
              setHoverX(e.clientX - rect.left);
              setHoverTime(computeTimeFromPointer(e.clientX));
            }}
            onMouseLeave={() => setHoverTime(null)}
            className="group relative h-5 w-full cursor-pointer flex items-center"
          >
            {/* Base Track */}
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-white/10 transition group-hover:h-2.5">
              {/* Flag / Safety Car / VSC spans */}
              {durationS > 0 &&
                manifest.race_events.map((ev, i) => {
                  if (ev.type === "dnf") return null;
                  const leftPct = (ev.time_s / durationS) * 100;
                  const endS = ev.end_time_s ?? ev.time_s + 15;
                  const widthPct = Math.max(
                    0.4,
                    ((endS - ev.time_s) / durationS) * 100
                  );
                  const bg =
                    ev.type === "red_flag"
                      ? "bg-red-500/80"
                      : ev.type === "safety_car"
                        ? "bg-amber-400/80"
                        : ev.type === "vsc"
                          ? "bg-orange-400/75"
                          : "bg-yellow-300/75";
                  return (
                    <div
                      key={`${ev.type}-${i}`}
                      className={`absolute inset-y-0 ${bg}`}
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                    />
                  );
                })}

              {/* Elapsed Playhead Bar */}
              <div
                className="relative h-full bg-[#E10600]"
                style={{ width: `${progressPct}%` }}
              />
            </div>

            {/* DNF Pin Markers */}
            {durationS > 0 &&
              manifest.race_events
                .filter((ev) => ev.type === "dnf")
                .map((ev, i) => {
                  const leftPct = (ev.time_s / durationS) * 100;
                  return (
                    <div
                      key={`dnf-${i}`}
                      title={`DNF: ${ev.label} (Lap ${ev.lap ?? "?"})`}
                      className="pointer-events-none absolute -top-1 h-3 w-[2px] bg-red-500"
                      style={{ left: `${leftPct}%` }}
                    />
                  );
                })}

            {/* Scrubber Thumb */}
            <div
              className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-[#E10600] shadow"
              style={{ left: `${progressPct}%` }}
            />

            {/* Hover Timestamp Tooltip */}
            {hoverTime !== null && (
              <div
                className="pointer-events-none absolute -top-7 -translate-x-1/2 rounded border border-white/15 bg-[#121621] px-2 py-0.5 font-mono text-[10px] text-white shadow-lg"
                style={{ left: hoverX }}
              >
                {formatRaceClock(hoverTime)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Transport + Speed + Pit Wall Toggles */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Playback Transport */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={restart}
            title="Restart Replay (R)"
            className="cursor-pointer rounded border border-white/10 bg-white/[0.04] p-1.5 text-slate-300 transition hover:border-white/25 hover:bg-white/10 hover:text-white"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => skipBy(-10)}
            title="Rewind 10s (←)"
            className="cursor-pointer rounded border border-white/10 bg-white/[0.04] p-1.5 text-slate-300 transition hover:border-white/25 hover:bg-white/10 hover:text-white"
          >
            <Rewind className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={togglePlay}
            title="Play / Pause (Space)"
            className="flex cursor-pointer items-center gap-1.5 rounded bg-[#E10600] px-3.5 py-1.5 font-display text-xs font-bold tracking-wider text-white uppercase transition hover:bg-[#ff1e17]"
          >
            {isPlaying ? (
              <>
                <Pause className="h-3.5 w-3.5 fill-current" /> Pause
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 fill-current" /> Play
              </>
            )}
          </button>
          <button
            onClick={() => skipBy(10)}
            title="Fast Forward 10s (→)"
            className="cursor-pointer rounded border border-white/10 bg-white/[0.04] p-1.5 text-slate-300 transition hover:border-white/25 hover:bg-white/10 hover:text-white"
          >
            <FastForward className="h-3.5 w-3.5" />
          </button>

          <span className="ml-2 font-mono text-xs text-slate-300 tabular-nums">
            {formatRaceClock(currentTimeS)}
            <span className="text-slate-600"> / </span>
            <span className="text-slate-500">{formatRaceClock(durationS)}</span>
          </span>
        </div>

        {/* Center: Speed Selector */}
        <div className="flex items-center gap-1 rounded-md border border-white/8 bg-[#0F131D] p-1">
          {[0.5, 1, 2, 4, 8, 16, 32, 64].map((spd) => (
            <button
              key={spd}
              onClick={() => setPlaybackSpeed(spd)}
              className={`cursor-pointer rounded px-2 py-0.5 font-mono text-[11px] font-semibold transition ${
                playbackSpeed === spd
                  ? "bg-white text-[#090B10]"
                  : "text-slate-400 hover:bg-white/8 hover:text-white"
              }`}
            >
              {spd}x
            </button>
          ))}
          {!([0.5, 1, 2, 4, 8, 16, 32, 64] as number[]).includes(playbackSpeed) && (
            <span className="rounded bg-white px-2 py-0.5 font-mono text-[11px] font-bold text-[#090B10]">
              {playbackSpeed}x
            </span>
          )}
        </div>

        {/* Right: Pit Wall Layer & Standings Toggles */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={toggleDrsZones}
            title="Toggle DRS Zones (D)"
            className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase transition ${
              showDrsZones
                ? "border-[#00E676]/40 bg-[#00E676]/15 text-[#00E676]"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <Zap className="h-3 w-3" /> DRS
          </button>

          <button
            onClick={toggleDriverLabels}
            title="Toggle Driver Labels on Track (L)"
            className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase transition ${
              showDriverLabels
                ? "border-sky-400/40 bg-sky-400/15 text-sky-300"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <Tag className="h-3 w-3" /> Tags
          </button>

          <button
            onClick={toggleLeaderboard}
            title="Toggle Timing Leaderboard (T)"
            className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase transition ${
              showLeaderboard
                ? "border-[#E10600]/50 bg-[#E10600]/20 text-red-200"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <ListOrdered className="h-3 w-3" /> Timing
          </button>

          <button
            onClick={() => setActiveOverlay("drivers_champ")}
            title="Drivers' Championship (C)"
            className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase transition ${
              activeOverlay === "drivers_champ"
                ? "border-amber-400/50 bg-amber-400/20 text-amber-300"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <Trophy className="h-3 w-3" /> WDC
          </button>

          <button
            onClick={() => setActiveOverlay("constructors_champ")}
            title="Constructors' Championship (A)"
            className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase transition ${
              activeOverlay === "constructors_champ"
                ? "border-amber-400/50 bg-amber-400/20 text-amber-300"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <Award className="h-3 w-3" /> WCC
          </button>

          <button
            onClick={() => setActiveOverlay("controls_help")}
            title="Keyboard Controls (H)"
            className={`cursor-pointer rounded border p-1.5 transition ${
              activeOverlay === "controls_help"
                ? "border-white/40 bg-white/15 text-white"
                : "border-white/10 bg-white/[0.03] text-slate-400 hover:text-white"
            }`}
          >
            <HelpCircle className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </footer>
  );
};
