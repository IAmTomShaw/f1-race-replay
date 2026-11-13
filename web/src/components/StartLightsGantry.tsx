"use client";

import React, { useEffect, useState } from "react";
import { useReplayStore } from "@/store/useReplayStore";

export const StartLightsGantry: React.FC = () => {
  const manifest = useReplayStore((s) => s.manifest);
  const launchTimeS = useReplayStore((s) => s.launchTimeS);
  const preRollS = useReplayStore((s) => s.preRollS);
  const isPlaying = useReplayStore((s) => s.isPlaying);
  const snapshotTimeS = useReplayStore((s) => s.snapshot?.timeS ?? 0);
  const preRollSnapshot = useReplayStore((s) => s.preRollElapsedS);

  const [gantryT, setGantryT] = useState(0);

  const totalLaunchT = launchTimeS + preRollS;

  // Sync at 60 FPS while playing during the start sequence
  useEffect(() => {
    const readGantryT = () => {
      const s = useReplayStore.getState();
      return s.preRollElapsedS + s.currentTimeS;
    };

    setGantryT(readGantryT());
    if (!isPlaying) return;

    let rafId = 0;
    const tick = () => {
      const t = readGantryT();
      setGantryT(t);
      if (t <= totalLaunchT + 2.8 && useReplayStore.getState().isPlaying) {
        rafId = requestAnimationFrame(tick);
      }
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [isPlaying, totalLaunchT]);

  if (!manifest) return null;

  const t = isPlaying ? gantryT : preRollSnapshot + snapshotTimeS;
  const effectiveLaunchT = Math.max(5.8, totalLaunchT);
  const fadeOutStart = effectiveLaunchT + 1.7;
  const fadeOutEnd = effectiveLaunchT + 2.5;
  if (t > fadeOutEnd) return null;

  // Official FIA Sporting Regulations (Art. B5.7.1b):
  // Five red lights illuminate sequentially at exact 1.0s intervals,
  // followed by a 0.2s–3.0s hold before all five extinguish together.
  const stepS = 1.0;
  const holdS = Math.max(0.8, Math.min(2.2, effectiveLaunchT - 4.3));
  const firstLightT = Math.max(0.3, effectiveLaunchT - holdS - 4 * stepS);

  const isLightsOut = t >= effectiveLaunchT;
  let litCount = 0;
  if (!isLightsOut) {
    for (let i = 0; i < 5; i++) {
      if (t >= firstLightT + i * stepS) {
        litCount = i + 1;
      }
    }
  }

  const opacity =
    t >= fadeOutStart
      ? Math.max(0, 1 - (t - fadeOutStart) / (fadeOutEnd - fadeOutStart))
      : 1;

  const statusText = isLightsOut
    ? "LIGHTS OUT & AWAY WE GO"
    : litCount === 5
      ? "HOLD..."
      : litCount > 0
        ? `STANDING START • ${litCount}/5`
        : isPlaying
          ? "FORMATION COMPLETE"
          : "GRID READY • PRESS PLAY";

  return (
    <div
      style={{ opacity }}
      className="pointer-events-none absolute top-3 left-1/2 z-20 -translate-x-1/2 select-none transition-opacity duration-150"
    >
      <div className="flex flex-col items-center gap-1.5 rounded-lg border border-white/12 bg-[#090C12]/90 px-4 py-2.5 shadow-2xl backdrop-blur-md">
        {/* Gantry Support Bar + 5 Dual-Lamp Pods */}
        <div className="relative flex items-center gap-2.5">
          <div className="absolute inset-x-1 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-zinc-800" />
          {[0, 1, 2, 3, 4].map((podIdx) => {
            const isLit = !isLightsOut && podIdx < litCount;
            return (
              <div
                key={podIdx}
                className="relative z-10 flex flex-col gap-1.5 rounded-md border border-white/10 bg-[#121620] p-1.5 shadow-inner"
              >
                {/* Upper bulb (dim standby) */}
                <span
                  className={`h-3 w-3 rounded-full border transition-all duration-75 ${
                    isLit
                      ? "border-red-400/70 bg-red-600/45 shadow-[0_0_8px_rgba(239,68,68,0.45)]"
                      : "border-zinc-700/80 bg-zinc-900"
                  }`}
                />
                {/* Primary Red Start Bulb */}
                <span
                  className={`h-3.5 w-3.5 rounded-full border transition-all duration-75 ${
                    isLit
                      ? "border-red-300 bg-[#FF1E1E] shadow-[0_0_14px_rgba(255,30,30,0.95)]"
                      : "border-zinc-700 bg-zinc-950"
                  }`}
                />
              </div>
            );
          })}
        </div>

        {/* Status Caption */}
        <span
          className={`font-mono text-[10px] font-bold tracking-[0.18em] uppercase ${
            isLightsOut
              ? "text-[#00E676]"
              : litCount > 0
                ? "text-red-400"
                : "text-slate-400"
          }`}
        >
          {statusText}
        </span>
      </div>
    </div>
  );
};
