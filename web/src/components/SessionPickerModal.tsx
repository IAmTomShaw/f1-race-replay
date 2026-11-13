"use client";

import React, { useEffect, useState } from "react";
import { X, Play, Server, Sparkles, CheckCircle2, Loader2 } from "lucide-react";
import { useReplayStore } from "@/store/useReplayStore";
import { fetchSeasons, fetchSeasonSchedule, getApiBaseUrl } from "@/lib/api";
import { SeasonEventItem } from "@/types/replay";

export const SessionPickerModal: React.FC = () => {
  const activeOverlay = useReplayStore((s) => s.activeOverlay);
  const backendOnline = useReplayStore((s) => s.backendOnline);
  const setActiveOverlay = useReplayStore((s) => s.setActiveOverlay);
  const loadDemo = useReplayStore((s) => s.loadDemo);
  const loadFastF1Session = useReplayStore((s) => s.loadFastF1Session);

  const [seasons, setSeasons] = useState<number[]>([2026, 2025, 2024, 2023]);
  const [selectedYear, setSelectedYear] = useState<number>(2026);
  const [seasonsInitialized, setSeasonsInitialized] = useState(false);
  const [events, setEvents] = useState<SeasonEventItem[]>([]);
  const [loadingSchedule, setLoadingSchedule] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const isOpen = activeOverlay === "session_picker";

  useEffect(() => {
    if (!isOpen) return;
    useReplayStore.getState().refreshBackendStatus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !backendOnline || seasonsInitialized) return;
    let cancelled = false;

    fetchSeasons()
      .then((data) => {
        if (!cancelled) {
          setSeasons(data.seasons);
          setSelectedYear(data.default_year);
          setSeasonsInitialized(true);
        }
      })
      .catch(() => {
        if (!cancelled) setSeasonsInitialized(true);
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, backendOnline, seasonsInitialized]);

  useEffect(() => {
    if (!isOpen || !backendOnline || !seasonsInitialized) return;
    let cancelled = false;
    setLoadingSchedule(true);
    setScheduleError(null);

    fetchSeasonSchedule(selectedYear)
      .then((evts) => {
        if (!cancelled) {
          setEvents(evts);
          setLoadingSchedule(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setScheduleError(
            err instanceof Error ? err.message : "Failed to load schedule"
          );
          setLoadingSchedule(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, backendOnline, selectedYear]);

  if (!isOpen) return null;

  const apiBase = getApiBaseUrl();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-white/12 bg-[#0D111A] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div>
            <h2 className="font-display text-base font-bold tracking-wider text-white uppercase">
              Select Grand Prix Session
            </h2>
            <p className="mt-0.5 font-mono text-xs text-slate-400">
              Load any historical Formula 1 Race or Sprint via FastF1
            </p>
          </div>
          <button
            onClick={() => setActiveOverlay("none")}
            className="cursor-pointer rounded p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Instant Demo Card */}
        <div className="border-b border-white/8 bg-white/[0.02] px-5 py-3.5">
          <div className="flex items-center justify-between gap-4 rounded-md border border-[#00E676]/30 bg-[#00E676]/8 px-4 py-3">
            <div className="flex items-center gap-3">
              <Sparkles className="h-5 w-5 shrink-0 text-[#00E676]" />
              <div>
                <div className="font-display text-sm font-bold text-white">
                  Instant 20-Car Grand Prix Showcase
                </div>
                <div className="font-mono text-[11px] text-slate-300">
                  8 laps • DRS zones • Pit stops • Safety Car deployment • Loads in &lt;100ms
                </div>
              </div>
            </div>
            <button
              onClick={() => loadDemo()}
              className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded bg-[#00E676] px-3.5 py-1.5 font-display text-xs font-bold tracking-wider text-[#090B10] uppercase transition hover:bg-[#33eb91]"
            >
              <Play className="h-3.5 w-3.5 fill-current" /> Launch
            </button>
          </div>
        </div>

        {/* FastF1 Archive Browser */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!backendOnline ? (
            <div className="rounded-md border border-amber-400/25 bg-amber-400/8 p-4 font-mono text-xs text-slate-300">
              <div className="flex items-center gap-2 font-bold text-amber-300">
                <Server className="h-4 w-4" /> FastAPI Telemetry Backend Offline
              </div>
              <p className="mt-2 leading-relaxed text-slate-400">
                The web frontend is currently running in standalone mode using the built-in showcase bundle. To load full 2018–2026 FastF1 sessions:
              </p>
              <pre className="mt-2.5 overflow-x-auto rounded bg-black/50 p-2.5 text-[11px] text-emerald-300">
                .venv/bin/uvicorn backend.app:app --reload --port 8000
              </pre>
              <p className="mt-2 text-[11px] text-slate-500">
                Configured endpoint: {apiBase || "/api (proxied to http://127.0.0.1:8000)"}
              </p>
            </div>
          ) : (
            <>
              {/* Season Selector */}
              <div className="mb-4 flex flex-wrap items-center gap-1.5">
                {seasons.map((yr) => (
                  <button
                    key={yr}
                    onClick={() => setSelectedYear(yr)}
                    className={`cursor-pointer rounded px-3 py-1 font-mono text-xs font-bold transition ${
                      selectedYear === yr
                        ? "bg-[#E10600] text-white"
                        : "border border-white/10 bg-white/[0.03] text-slate-300 hover:bg-white/10"
                    }`}
                  >
                    {yr}
                  </button>
                ))}
              </div>

              {loadingSchedule ? (
                <div className="flex items-center justify-center gap-2 py-12 font-mono text-xs text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin text-[#E10600]" />
                  Loading {selectedYear} FIA Event Calendar...
                </div>
              ) : scheduleError ? (
                <div className="rounded border border-red-500/30 bg-red-500/10 p-3 font-mono text-xs text-red-300">
                  {scheduleError}
                </div>
              ) : (
                <div className="space-y-2">
                  {events.map((ev) => {
                    const isCompleted = ev.is_completed !== false;
                    return (
                      <div
                        key={ev.round_number}
                        className={`flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/8 bg-[#121723] px-3.5 py-2.5 transition ${
                          isCompleted ? "hover:border-white/20" : "opacity-50"
                        }`}
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="rounded bg-white/8 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-300">
                              R{String(ev.round_number).padStart(2, "0")}
                            </span>
                            <span className="font-display text-sm font-bold text-white">
                              {ev.event_name}
                            </span>
                          </div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                            {ev.country} • {ev.date}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {!isCompleted ? (
                            <span className="rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                              Upcoming
                            </span>
                          ) : (
                            ev.sessions.map((sType) => {
                              const isCached = ev.cached_sessions.includes(sType);
                              return (
                                <button
                                  key={sType}
                                  onClick={() =>
                                    loadFastF1Session(
                                      selectedYear,
                                      ev.round_number,
                                      sType
                                    )
                                  }
                                  className="flex cursor-pointer items-center gap-1.5 rounded border border-white/15 bg-white/6 px-3 py-1 font-mono text-xs font-semibold text-white transition hover:border-[#E10600] hover:bg-[#E10600]"
                                >
                                  {isCached && (
                                    <CheckCircle2 className="h-3 w-3 text-[#00E676]" />
                                  )}
                                  {sType === "S" ? "Sprint" : "Race"}
                                </button>
                              );
                            })
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
