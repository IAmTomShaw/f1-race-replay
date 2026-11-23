"use client";

import React from "react";
import { Radio, Gauge, X } from "lucide-react";
import { useReplayStore } from "@/store/useReplayStore";
import { formatRaceClock, getTyreMeta } from "@/lib/interpolation";

export const TelemetryInspector: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const snapshot = useReplayStore((s) => s.snapshot);
  const selectedDrivers = useReplayStore((s) => s.selectedDrivers);
  const selectDriver = useReplayStore((s) => s.selectDriver);

  if (!manifest || !snapshot) {
    return null;
  }

  return (
    <aside className="flex h-full w-full flex-col border-r border-white/8 bg-[#0B0E15]/95 backdrop-blur-md lg:w-[308px]">
      {/* Selected Drivers Telemetry Section */}
      <div className="flex items-center justify-between border-b border-white/8 px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <Gauge className="h-3.5 w-3.5 text-[#00E676]" />
          <h2 className="font-display text-xs font-bold tracking-[0.16em] text-white uppercase">
            Car Telemetry
          </h2>
        </div>
        <span className="font-mono text-[10px] text-slate-500">
          {selectedDrivers.length}/4 SELECTED
        </span>
      </div>

      <div className="flex-1 space-y-2.5 overflow-y-auto p-3">
        {selectedDrivers.length === 0 ? (
          <div className="rounded-md border border-dashed border-white/12 bg-white/[0.02] px-3 py-6 text-center font-mono text-xs text-slate-400">
            Select a car on the track or leaderboard to inspect live telemetry.
          </div>
        ) : (
          selectedDrivers.map((code) => {
            const drv = snapshot.driversByCode[code];
            const meta = manifest.drivers[code];
            if (!drv) return null;
            const color = meta?.color || "#9CA3AF";
            const tyre = getTyreMeta(drv.tyre);
            const brakePct = Math.min(
              100,
              drv.brake <= 1 ? drv.brake * 100 : drv.brake
            );

            return (
              <div
                key={code}
                className="relative overflow-hidden rounded-md border border-white/10 bg-[#111520] p-3"
              >
                {/* Top team accent stripe */}
                <div
                  className="absolute inset-x-0 top-0 h-[2px]"
                  style={{ backgroundColor: color }}
                />

                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-slate-400">
                        P{drv.position}
                      </span>
                      <span className="font-display text-sm font-bold tracking-wider text-white">
                        {meta?.full_name || code}
                      </span>
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-slate-400">
                      #{meta?.number} • {meta?.team}
                    </div>
                  </div>

                  <button
                    onClick={() => selectDriver(code, true)}
                    className="cursor-pointer rounded p-0.5 text-slate-500 transition hover:bg-white/8 hover:text-white"
                    title="Remove from inspector"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Speed / Gear / DRS / Tyre Readout */}
                <div className="mt-3 grid grid-cols-4 gap-1.5 rounded bg-[#090B10] p-2">
                  <div>
                    <div className="font-mono text-[9px] text-slate-500 uppercase">
                      SPEED
                    </div>
                    <div className="font-mono text-base font-bold text-white tabular-nums">
                      {Math.round(drv.speed)}
                    </div>
                    <div className="font-mono text-[8px] text-slate-500">KM/H</div>
                  </div>

                  <div>
                    <div className="font-mono text-[9px] text-slate-500 uppercase">
                      GEAR
                    </div>
                    <div className="font-mono text-base font-bold text-white tabular-nums">
                      {drv.isOut ? "N" : drv.gear || "N"}
                    </div>
                    <div className="font-mono text-[8px] text-slate-500">
                      LAP {drv.lap}
                    </div>
                  </div>

                  <div>
                    <div className="font-mono text-[9px] text-slate-500 uppercase">
                      DRS
                    </div>
                    <div
                      className={`mt-0.5 inline-flex rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                        drv.drsActive
                          ? "bg-[#00E676]/20 text-[#00E676]"
                          : "bg-white/6 text-slate-500"
                      }`}
                    >
                      {drv.drsActive ? "OPEN" : "OFF"}
                    </div>
                  </div>

                  <div>
                    <div className="font-mono text-[9px] text-slate-500 uppercase">
                      TYRE
                    </div>
                    <div className="mt-0.5 flex items-center gap-1">
                      <span
                        className="inline-flex h-4 w-4 items-center justify-center rounded-full border font-mono text-[9px] font-bold"
                        style={{ borderColor: tyre.color, color: tyre.color }}
                      >
                        {tyre.short}
                      </span>
                      <span className="font-mono text-[11px] font-semibold text-slate-200 tabular-nums">
                        {drv.tyre_life}L
                      </span>
                    </div>
                  </div>
                </div>

                {/* Throttle & Brake Pedal Bars */}
                <div className="mt-2.5 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-8 font-mono text-[9px] text-slate-400">
                      THR
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/8">
                      <div
                        className="h-full rounded-full bg-[#00E676] transition-[width] duration-75"
                        style={{
                          width: `${Math.max(0, Math.min(100, drv.throttle))}%`,
                        }}
                      />
                    </div>
                    <span className="w-8 text-right font-mono text-[9px] text-slate-300 tabular-nums">
                      {Math.round(drv.throttle)}%
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="w-8 font-mono text-[9px] text-slate-400">
                      BRK
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/8">
                      <div
                        className="h-full rounded-full bg-[#FF3B30] transition-[width] duration-75"
                        style={{ width: `${brakePct}%` }}
                      />
                    </div>
                    <span className="w-8 text-right font-mono text-[9px] text-slate-300 tabular-nums">
                      {Math.round(brakePct)}%
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* FIA Race Control Feed */}
      <div className="flex h-52 flex-col border-t border-white/8 bg-[#090B10]/90">
        <div className="flex items-center justify-between border-b border-white/6 px-3.5 py-2">
          <div className="flex items-center gap-1.5">
            <Radio className="h-3.5 w-3.5 text-amber-400" />
            <span className="font-display text-[11px] font-bold tracking-[0.14em] text-slate-200 uppercase">
              Race Control
            </span>
          </div>
          <span className="font-mono text-[10px] text-slate-500">FIA FEED</span>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto px-3 py-2">
          {snapshot.recentMessages.length === 0 ? (
            <div className="py-4 text-center font-mono text-[11px] text-slate-500">
              No race control messages yet.
            </div>
          ) : (
            snapshot.recentMessages.map((msg, i) => {
              const isAlert =
                msg.flag === "YELLOW" ||
                msg.flag === "RED" ||
                msg.category === "SafetyCar";
              return (
                <div
                  key={`${msg.time}-${i}`}
                  className={`rounded border px-2.5 py-1.5 font-mono text-[10px] leading-relaxed ${
                    isAlert
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                      : "border-white/6 bg-white/[0.02] text-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between text-[9px] text-slate-500">
                    <span>{formatRaceClock(msg.time)}</span>
                    <span className="uppercase">{msg.category || "INFO"}</span>
                  </div>
                  <div className="mt-0.5 font-medium">{msg.message}</div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
};
