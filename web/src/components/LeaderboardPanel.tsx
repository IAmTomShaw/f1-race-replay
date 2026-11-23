"use client";

import React from "react";
import { useReplayStore } from "@/store/useReplayStore";
import { getTyreMeta } from "@/lib/interpolation";

export const LeaderboardPanel: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const snapshot = useReplayStore((s) => s.snapshot);
  const selectedDrivers = useReplayStore((s) => s.selectedDrivers);
  const gapMode = useReplayStore((s) => s.gapMode);
  const toggleGapMode = useReplayStore((s) => s.toggleGapMode);
  const selectDriver = useReplayStore((s) => s.selectDriver);

  if (!manifest || !snapshot) {
    return (
      <aside className="flex h-full w-72 flex-col border-l border-white/8 bg-[#0C0F16]/95 p-4">
        <div className="h-5 w-32 animate-pulse rounded bg-white/8" />
      </aside>
    );
  }

  const selectedSet = new Set(selectedDrivers);

  return (
    <aside className="flex h-full w-full flex-col border-t border-white/8 bg-[#0B0E15]/95 backdrop-blur-md md:w-[272px] md:border-t-0 md:border-l lg:w-[292px]">
      {/* Timing Tower Header */}
      <div className="flex items-center justify-between border-b border-white/8 px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-[#E10600]" />
          <h2 className="font-display text-xs font-bold tracking-[0.16em] text-white uppercase">
            Live Timing
          </h2>
        </div>
        <button
          onClick={toggleGapMode}
          title="Switch between Gap to Leader and Interval"
          className="cursor-pointer rounded border border-white/12 bg-white/5 px-2 py-0.5 font-mono text-[10px] font-medium tracking-wider text-slate-300 uppercase transition hover:border-white/25 hover:bg-white/10 hover:text-white"
        >
          {gapMode === "leader" ? "GAP" : "INT"}
        </button>
      </div>

      {/* Column Subheader */}
      <div className="grid grid-cols-[26px_1fr_64px_46px] items-center border-b border-white/6 bg-white/[0.02] px-3 py-1 font-mono text-[9px] tracking-widest text-slate-500 uppercase">
        <span>POS</span>
        <span>DRIVER</span>
        <span className="text-right">{gapMode === "leader" ? "LEADER" : "INTERVAL"}</span>
        <span className="text-right">TYRE</span>
      </div>

      {/* 20-Driver Timing Rows */}
      <div className="flex-1 overflow-y-auto py-1">
        {snapshot.driversSorted.map((drv) => {
          const meta = manifest.drivers[drv.code];
          const color = meta?.color || "#9CA3AF";
          const isSelected = selectedSet.has(drv.code);
          const tyre = getTyreMeta(drv.tyre);
          const deltaText =
            gapMode === "leader" ? drv.gapToLeader : drv.intervalAhead;

          return (
            <button
              key={drv.code}
              onClick={(e) => selectDriver(drv.code, e.shiftKey || e.metaKey)}
              className={`group grid w-full cursor-pointer grid-cols-[26px_1fr_64px_46px] items-center px-3 py-[5px] text-left transition ${
                isSelected
                  ? "bg-white/12 text-white"
                  : "hover:bg-white/[0.05] text-slate-200"
              } ${drv.isOut ? "opacity-45" : ""}`}
            >
              {/* Position */}
              <span
                className={`font-mono text-[11px] font-bold ${
                  drv.position === 1
                    ? "text-[#FFD60A]"
                    : drv.position <= 3
                      ? "text-white"
                      : "text-slate-400"
                }`}
              >
                {drv.position}
              </span>

              {/* Team Bar + Driver Code + Status Badges */}
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-3.5 w-[3px] shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="font-mono text-xs font-bold tracking-wide text-white">
                  {drv.code}
                </span>
                {drv.drsActive && !drv.isOut && !drv.inPit && (
                  <span className="rounded bg-[#00E676]/20 px-1 py-[1px] font-mono text-[8px] font-bold text-[#00E676]">
                    DRS
                  </span>
                )}
                {drv.inPit && (
                  <span className="rounded bg-amber-400/20 px-1 py-[1px] font-mono text-[9px] font-bold text-amber-300">
                    PIT
                  </span>
                )}
                {drv.isOut && (
                  <span className="rounded bg-red-500/25 px-1 py-[1px] font-mono text-[9px] font-bold text-red-400">
                    OUT
                  </span>
                )}
              </div>

              {/* Gap / Interval */}
              <span
                className={`text-right font-mono text-[11px] tabular-nums ${
                  drv.position === 1 && deltaText === "LEADER"
                    ? "text-[10px] font-semibold text-slate-400"
                    : drv.isOut
                      ? "font-bold text-red-400"
                      : "text-slate-300"
                }`}
              >
                {drv.position === 1 && deltaText === "LEADER" ? "—" : deltaText}
              </span>

              {/* Tyre Compound Ring + Stint Age */}
              <div className="flex items-center justify-end gap-1">
                <span className="font-mono text-[10px] text-slate-400 tabular-nums">
                  {`${drv.tyre_life}`}
                </span>
                <span
                  title={`${tyre.name} (${drv.tyre_life} laps)`}
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border-[1.5px] font-mono text-[9px] font-extrabold"
                  style={{
                    borderColor: tyre.color,
                    color: tyre.color,
                    backgroundColor: "rgba(9, 11, 16, 0.9)",
                  }}
                >
                  {tyre.short}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer Hint */}
      <div className="border-t border-white/6 px-3 py-1.5 font-mono text-[10px] text-slate-500">
        Click to inspect • <span className="text-slate-400">Shift+Click</span> multi-select
      </div>
    </aside>
  );
};
