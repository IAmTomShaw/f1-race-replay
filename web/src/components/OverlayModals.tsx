"use client";

import React from "react";
import { X, Trophy, Award, Keyboard } from "lucide-react";
import { useReplayStore } from "@/store/useReplayStore";

const POINTS_BY_POS: Record<number, number> = {
  1: 25,
  2: 18,
  3: 15,
  4: 12,
  5: 10,
  6: 8,
  7: 6,
  8: 4,
  9: 2,
  10: 1,
};

export const OverlayModals: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const snapshot = useReplayStore((s) => s.snapshot);
  const activeOverlay = useReplayStore((s) => s.activeOverlay);
  const setActiveOverlay = useReplayStore((s) => s.setActiveOverlay);

  if (
    !manifest ||
    !snapshot ||
    activeOverlay === "none" ||
    activeOverlay === "session_picker"
  ) {
    return null;
  }

  if (activeOverlay === "controls_help") {
    const shortcuts = [
      ["Space", "Play / Pause replay"],
      ["← / →", "Rewind / Fast-Forward 10s"],
      ["↑ / ↓", "Increase / Decrease playback speed"],
      ["1 – 4", "Set speed (0.5x, 1x, 2x, 4x)"],
      ["R", "Restart session from Lap 1"],
      ["D", "Toggle DRS Zones on circuit"],
      ["L", "Toggle driver code tags on track"],
      ["T", "Toggle Timing Leaderboard panel"],
      ["B", "Toggle timeline progress bar"],
      ["I", "Toggle top session banner"],
      ["C", "Live Drivers' Championship (WDC)"],
      ["A", "Live Constructors' Championship (WCC)"],
      ["Click / Shift+Click", "Inspect single or multiple drivers"],
    ];

    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/65 p-4 backdrop-blur-xs">
        <div className="w-full max-w-md rounded-lg border border-white/12 bg-[#0E121B] p-5 shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/8 pb-3">
            <div className="flex items-center gap-2">
              <Keyboard className="h-4 w-4 text-[#E10600]" />
              <h3 className="font-display text-sm font-bold tracking-wider text-white uppercase">
                Pit Wall Keyboard Shortcuts
              </h3>
            </div>
            <button
              onClick={() => setActiveOverlay("none")}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-3 space-y-1.5">
            {shortcuts.map(([key, desc]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded bg-white/[0.02] px-2.5 py-1.5 font-mono text-xs"
              >
                <span className="rounded border border-white/15 bg-black/40 px-2 py-0.5 text-[11px] font-bold text-white">
                  {key}
                </span>
                <span className="text-slate-300">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Compute live projected WDC or WCC points from current on-track positions
  if (activeOverlay === "drivers_champ") {
    const lapKey = String(snapshot.leaderLap);
    const precomputed = manifest.standings.live_drivers?.[lapKey];
    const base = manifest.standings.current_drivers || {};

    const rows = Object.keys(manifest.drivers).map((code) => {
      const drv = snapshot.driversByCode[code];
      const pos = drv?.position ?? 20;
      const gained = drv?.isOut ? 0 : POINTS_BY_POS[pos] || 0;
      const startPts = base[code] ?? 0;
      const totalPts = precomputed?.[code] ?? startPts + gained;
      return {
        code,
        name: manifest.drivers[code]?.full_name || code,
        color: manifest.drivers[code]?.color || "#9CA3AF",
        totalPts,
        gained,
      };
    });
    rows.sort((a, b) => b.totalPts - a.totalPts);

    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/65 p-4 backdrop-blur-xs">
        <div className="flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-lg border border-white/12 bg-[#0E121B] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/8 px-5 py-3.5">
            <div className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-amber-400" />
              <h3 className="font-display text-sm font-bold tracking-wider text-white uppercase">
                Live Drivers&apos; Championship
              </h3>
            </div>
            <button
              onClick={() => setActiveOverlay("none")}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-1">
            {rows.map((r, idx) => (
              <div
                key={r.code}
                className="flex items-center justify-between rounded bg-white/[0.03] px-3 py-1.5 font-mono text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <span className="w-5 text-slate-400">{idx + 1}</span>
                  <span
                    className="h-3.5 w-1 rounded-full"
                    style={{ backgroundColor: r.color }}
                  />
                  <span className="font-bold text-white">{r.code}</span>
                  <span className="text-[11px] text-slate-400">{r.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  {r.gained > 0 && (
                    <span className="text-[10px] text-[#00E676]">
                      +{r.gained}
                    </span>
                  )}
                  <span className="font-bold text-white tabular-nums">
                    {r.totalPts}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (activeOverlay === "constructors_champ") {
    const baseCon = manifest.standings.current_constructors || {};
    const teamGains: Record<string, { gained: number; color: string }> = {};

    for (const [code, meta] of Object.entries(manifest.drivers)) {
      if (!meta.team) continue;
      const drv = snapshot.driversByCode[code];
      const gained = drv && !drv.isOut ? POINTS_BY_POS[drv.position] || 0 : 0;
      if (!teamGains[meta.team]) {
        teamGains[meta.team] = { gained: 0, color: meta.color };
      }
      teamGains[meta.team].gained += gained;
    }

    const allTeams = new Set([...Object.keys(baseCon), ...Object.keys(teamGains)]);
    const rows = Array.from(allTeams).map((team) => {
      const startPts = baseCon[team] ?? 0;
      const gained = teamGains[team]?.gained ?? 0;
      return {
        team,
        color: teamGains[team]?.color || "#9CA3AF",
        totalPts: startPts + gained,
        gained,
      };
    });
    rows.sort((a, b) => b.totalPts - a.totalPts);

    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/65 p-4 backdrop-blur-xs">
        <div className="flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-lg border border-white/12 bg-[#0E121B] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/8 px-5 py-3.5">
            <div className="flex items-center gap-2">
              <Award className="h-4 w-4 text-amber-400" />
              <h3 className="font-display text-sm font-bold tracking-wider text-white uppercase">
                Live Constructors&apos; Championship
              </h3>
            </div>
            <button
              onClick={() => setActiveOverlay("none")}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
            {rows.map((r, idx) => (
              <div
                key={r.team}
                className="flex items-center justify-between rounded bg-white/[0.03] px-3 py-2 font-mono text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <span className="w-5 text-slate-400">{idx + 1}</span>
                  <span
                    className="h-3.5 w-1 rounded-full"
                    style={{ backgroundColor: r.color }}
                  />
                  <span className="font-bold text-white">{r.team}</span>
                </div>
                <div className="flex items-center gap-2">
                  {r.gained > 0 && (
                    <span className="text-[10px] text-[#00E676]">
                      +{r.gained}
                    </span>
                  )}
                  <span className="font-bold text-white tabular-nums">
                    {r.totalPts}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return null;
};
