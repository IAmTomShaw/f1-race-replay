"use client";

import React from "react";
import {
  Calendar,
  Thermometer,
  Wind,
  Droplets,
  Flag,
} from "lucide-react";
import { useReplayStore } from "@/store/useReplayStore";
import {
  formatCompassDirection,
  getTrackStatusMeta,
} from "@/lib/interpolation";

export const TopSessionHeader: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const snapshot = useReplayStore((s) => s.snapshot);
  const showSessionBanner = useReplayStore((s) => s.showSessionBanner);
  const backendOnline = useReplayStore((s) => s.backendOnline);
  const setActiveOverlay = useReplayStore((s) => s.setActiveOverlay);

  if (!showSessionBanner || !manifest || !snapshot) return null;

  const info = manifest.session_info;
  const statusMeta = getTrackStatusMeta(snapshot.trackStatusCode);
  const w = snapshot.weather;

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 bg-[#0A0D13]/95 px-4 py-2.5 backdrop-blur-md">
      {/* Left: Brand + Event Identity + Session Switcher */}
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-[#E10600] font-display text-xs font-extrabold tracking-tighter text-white">
            F1
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-sm font-bold tracking-wide text-white uppercase">
                {info.event_name}
              </h1>
              <span className="rounded border border-white/12 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-300">
                {info.year} • {info.session_name}
              </span>
            </div>
            <div className="font-mono text-[10px] text-slate-400">
              {info.circuit_name} • {info.country}
              {info.circuit_length_m
                ? ` • ${(info.circuit_length_m / 1000).toFixed(3)} km`
                : ""}
            </div>
          </div>
        </div>

        <button
          onClick={() => setActiveOverlay("session_picker")}
          className="flex h-7 cursor-pointer items-center gap-1.5 rounded border border-white/15 bg-white/[0.05] px-2.5 font-mono text-[11px] font-semibold text-white transition hover:border-[#E10600] hover:bg-[#E10600]/20"
        >
          <Calendar className="h-3.5 w-3.5 text-[#E10600]" />
          Change Race
        </button>
      </div>

      {/* Center: Lap Counter + Track Status */}
      <div className="flex items-center gap-3">
        <div className="flex h-7 items-center gap-1.5 rounded border border-white/10 bg-[#111520] px-3">
          <span className="font-mono text-[10px] tracking-widest text-slate-400 uppercase">
            LAP
          </span>
          <span className="font-display text-xs font-extrabold text-white tabular-nums">
            {snapshot.leaderLap}
          </span>
          <span className="font-mono text-[11px] text-slate-500 tabular-nums">
            / {info.total_laps}
          </span>
        </div>

        <div
          className="flex h-7 items-center gap-1.5 rounded border px-3 font-display text-xs font-bold tracking-wider uppercase"
          style={{
            backgroundColor: statusMeta.badgeBg,
            color: statusMeta.badgeText,
            borderColor: `${statusMeta.badgeText}40`,
          }}
        >
          <Flag className="h-3.5 w-3.5" />
          {statusMeta.label}
        </div>
      </div>

      {/* Right: Live Weather Strip + API Status */}
      <div className="hidden items-center gap-3 font-mono text-[11px] text-slate-300 xl:flex">
        {w && (
          <div className="flex h-7 items-center gap-3 rounded border border-white/8 bg-white/[0.02] px-3">
            {w.trackTemp !== null && (
              <span className="flex items-center gap-1" title="Track / Air Temp">
                <Thermometer className="h-3.5 w-3.5 text-amber-400" />
                <span>TRK {w.trackTemp.toFixed(1)}°C</span>
                {w.airTemp !== null && (
                  <span className="text-slate-500">
                    / AIR {w.airTemp.toFixed(1)}°C
                  </span>
                )}
              </span>
            )}
            {w.windSpeed !== null && (
              <span className="flex items-center gap-1 text-slate-400">
                <Wind className="h-3.5 w-3.5 text-sky-400" />
                {w.windSpeed.toFixed(1)} m/s {formatCompassDirection(w.windDirection)}
              </span>
            )}
            <span
              className={`flex items-center gap-1 font-semibold ${
                w.isRaining ? "text-sky-400" : "text-emerald-400"
              }`}
            >
              <Droplets className="h-3 w-3" />
              {w.isRaining ? "WET" : "DRY"}
            </span>
          </div>
        )}

        <div
          title={
            backendOnline
              ? "FastF1 API Server Connected"
              : "Standalone Showcase Mode (Start FastAPI backend for full archive)"
          }
          className="flex h-7 items-center gap-1.5 rounded border border-white/8 bg-white/[0.02] px-2.5 text-[10px]"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              backendOnline ? "bg-[#00E676]" : "bg-amber-400"
            }`}
          />
          <span className="text-slate-400">
            {backendOnline ? "FASTF1 ONLINE" : "DEMO MODE"}
          </span>
        </div>
      </div>
    </header>
  );
};
