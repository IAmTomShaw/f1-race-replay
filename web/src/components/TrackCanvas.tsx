"use client";

import React, { useEffect, useRef } from "react";
import { useReplayStore } from "@/store/useReplayStore";
import { getTrackStatusMeta, sampleSnapshotAtTime } from "@/lib/interpolation";
import { TrackGeometry } from "@/types/replay";

interface Transform {
  worldCx: number;
  worldCy: number;
  cosRot: number;
  sinRot: number;
  scale: number;
  screenCx: number;
  screenCy: number;
}

function computeTrackTransform(
  track: TrackGeometry,
  width: number,
  height: number
): Transform {
  const padding = 0.07;
  const worldCx = (track.x_min + track.x_max) / 2;
  const worldCy = (track.y_min + track.y_max) / 2;
  const rad = ((track.rotation_deg || 0) * Math.PI) / 180;
  const cosRot = Math.cos(rad);
  const sinRot = Math.sin(rad);

  let minRx = Infinity;
  let maxRx = -Infinity;
  let minRy = Infinity;
  let maxRy = -Infinity;

  const updateBounds = (xs: number[], ys: number[]) => {
    for (let i = 0; i < xs.length; i++) {
      const tx = xs[i] - worldCx;
      const ty = ys[i] - worldCy;
      const rx = tx * cosRot - ty * sinRot;
      const ry = tx * sinRot + ty * cosRot;
      if (rx < minRx) minRx = rx;
      if (rx > maxRx) maxRx = rx;
      if (ry < minRy) minRy = ry;
      if (ry > maxRy) maxRy = ry;
    }
  };

  updateBounds(track.x_inner, track.y_inner);
  updateBounds(track.x_outer, track.y_outer);

  const worldW = Math.max(1, maxRx - minRx);
  const worldH = Math.max(1, maxRy - minRy);
  const usableW = Math.max(1, width * (1 - 2 * padding));
  const usableH = Math.max(1, height * (1 - 2 * padding));
  const scale = Math.min(usableW / worldW, usableH / worldH);

  // Offset center slightly if rotated bounds are asymmetric around (worldCx, worldCy)
  const rotMidX = (minRx + maxRx) / 2;
  const rotMidY = (minRy + maxRy) / 2;

  return {
    worldCx,
    worldCy,
    cosRot,
    sinRot,
    scale,
    screenCx: width / 2 - rotMidX * scale,
    screenCy: height / 2 + rotMidY * scale,
  };
}

function worldToScreen(x: number, y: number, tf: Transform): [number, number] {
  const tx = x - tf.worldCx;
  const ty = y - tf.worldCy;
  const rx = tx * tf.cosRot - ty * tf.sinRot;
  const ry = tx * tf.sinRot + ty * tf.cosRot;
  // Flip Y so North (+Y in F1 world coordinates) points UP on HTML5 Canvas
  return [tf.screenCx + rx * tf.scale, tf.screenCy - ry * tf.scale];
}

export const TrackCanvas: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const staticLayerRef = useRef<{
    canvas: OffscreenCanvas | HTMLCanvasElement | null;
    key: string;
    tf: Transform | null;
  }>({ canvas: null, key: "", tf: null });

  const carHitTargetsRef = useRef<
    Array<{ code: string; sx: number; sy: number; r: number }>
  >([]);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    let width = container.clientWidth;
    let height = container.clientHeight;
    let dpr = window.devicePixelRatio || 1;

    const resizeCanvas = () => {
      if (!container || !canvas) return;
      width = Math.max(100, container.clientWidth);
      height = Math.max(100, container.clientHeight);
      dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      staticLayerRef.current.key = ""; // invalidate static layer
    };

    resizeCanvas();
    const observer = new ResizeObserver(resizeCanvas);
    observer.observe(container);

    const buildStaticTrackLayer = (
      track: TrackGeometry,
      statusCode: string,
      showDrs: boolean
    ) => {
      const cacheKey = `${width}x${height}@${dpr}:${track.x_min}:${track.rotation_deg}:${statusCode}:${showDrs}`;
      if (staticLayerRef.current.key === cacheKey && staticLayerRef.current.canvas) {
        return;
      }

      const offCanvas = document.createElement("canvas");
      offCanvas.width = Math.floor(width * dpr);
      offCanvas.height = Math.floor(height * dpr);
      const ctx = offCanvas.getContext("2d");
      if (!ctx) return;

      ctx.scale(dpr, dpr);
      const tf = computeTrackTransform(track, width, height);

      const nIn = track.x_inner.length;
      const nOut = track.x_outer.length;
      if (nIn < 2 || nOut < 2) return;

      const inPts = track.x_inner.map((x, i) =>
        worldToScreen(x, track.y_inner[i], tf)
      );
      const outPts = track.x_outer.map((x, i) =>
        worldToScreen(x, track.y_outer[i], tf)
      );

      // 1. Subtle outer ambient shadow under circuit ribbon
      ctx.save();
      ctx.beginPath();
      outPts.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.closePath();
      for (let i = inPts.length - 1; i >= 0; i--) {
        const [px, py] = inPts[i];
        if (i === inPts.length - 1) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.fillStyle = "#171B26";
      ctx.shadowColor = "rgba(0, 0, 0, 0.75)";
      ctx.shadowBlur = 18;
      ctx.fill("evenodd");
      ctx.restore();

      // 2. Center racing line subtle guide
      if (track.x_ref.length > 2) {
        ctx.save();
        ctx.beginPath();
        track.x_ref.forEach((x, i) => {
          const [px, py] = worldToScreen(x, track.y_ref[i], tf);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.closePath();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 6]);
        ctx.stroke();
        ctx.restore();
      }

      // 3. Inner & outer track edge lines colored by active FIA Track Status
      const statusMeta = getTrackStatusMeta(statusCode);
      const drawLoop = (pts: [number, number][], stroke: string, lineWidth: number) => {
        ctx.beginPath();
        pts.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
        ctx.closePath();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineWidth;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
      };

      if (statusMeta.key !== "GREEN") {
        ctx.save();
        ctx.shadowColor = statusMeta.trackStroke;
        ctx.shadowBlur = 12;
        drawLoop(inPts, statusMeta.trackStroke, 2.5);
        drawLoop(outPts, statusMeta.trackStroke, 2.5);
        ctx.restore();
      } else {
        drawLoop(inPts, "#7B8498", 2.2);
        drawLoop(outPts, "#7B8498", 2.2);
      }

      // 4. DRS Zones along outer track edge
      if (showDrs && track.drs_zones.length > 0) {
        ctx.save();
        ctx.strokeStyle = "#00E676";
        ctx.shadowColor = "rgba(0, 230, 118, 0.65)";
        ctx.shadowBlur = 10;
        ctx.lineWidth = 3.6;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        for (const zone of track.drs_zones) {
          if (zone.x.length < 2) continue;
          ctx.beginPath();
          zone.x.forEach((zx, idx) => {
            const [px, py] = worldToScreen(zx, zone.y[idx], tf);
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.stroke();
        }
        ctx.restore();
      }

      // 5. Checkered Start / Finish Line across [inPts[0], outPts[0]]
      const [ix0, iy0] = inPts[0];
      const [ox0, oy0] = outPts[0];
      const dx = ox0 - ix0;
      const dy = oy0 - iy0;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len;
      const uy = dy / len;
      const ext = 6;
      const sx1 = ix0 - ux * ext;
      const sy1 = iy0 - uy * ext;
      const totalLen = len + ext * 2;
      const squares = 8;
      const stepLen = totalLen / squares;
      const nx = -uy;
      const ny = ux;
      const bandWidth = 3.2;

      for (let s = 0; s < squares; s++) {
        for (let col = 0; col < 2; col++) {
          const bx = sx1 + ux * (s * stepLen) + nx * (col - 1) * bandWidth;
          const by = sy1 + uy * (s * stepLen) + ny * (col - 1) * bandWidth;
          ctx.beginPath();
          ctx.moveTo(bx, by);
          ctx.lineTo(bx + ux * stepLen, by + uy * stepLen);
          ctx.lineTo(
            bx + ux * stepLen + nx * bandWidth,
            by + uy * stepLen + ny * bandWidth
          );
          ctx.lineTo(bx + nx * bandWidth, by + ny * bandWidth);
          ctx.closePath();
          ctx.fillStyle = (s + col) % 2 === 0 ? "#FFFFFF" : "#111318";
          ctx.fill();
        }
      }

      staticLayerRef.current = { canvas: offCanvas, key: cacheKey, tf };
    };

    let rafId = 0;
    let lastTimestamp = performance.now();

    const renderFrame = (now: number) => {
      const dt = Math.min(0.1, Math.max(0, (now - lastTimestamp) / 1000));
      lastTimestamp = now;

      const store = useReplayStore.getState();
      if (store.isPlaying) {
        store.advanceClock(dt);
      }

      const ctx = canvas.getContext("2d");
      if (!ctx) {
        rafId = requestAnimationFrame(renderFrame);
        return;
      }

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      if (!store.manifest || !store.frames) {
        ctx.restore();
        rafId = requestAnimationFrame(renderFrame);
        return;
      }

      const snap = sampleSnapshotAtTime(
        store.manifest,
        store.frames,
        store.currentTimeS
      );

      buildStaticTrackLayer(
        store.manifest.track,
        snap.trackStatusCode,
        store.showDrsZones
      );

      const staticData = staticLayerRef.current;
      if (staticData.canvas && staticData.tf) {
        ctx.drawImage(staticData.canvas, 0, 0, width, height);
        const tf = staticData.tf;
        const selectedSet = new Set(store.selectedDrivers);
        const hitTargets: Array<{
          code: string;
          sx: number;
          sy: number;
          r: number;
        }> = [];

        // Draw cars from last place to P1 so leaders & selected drivers render cleanly on top
        const drawOrder = [...snap.driversSorted].reverse();

        for (const car of drawOrder) {
          const meta = store.manifest.drivers[car.code];
          const color = meta?.color || "#E5E7EB";
          const [sx, sy] = worldToScreen(car.x, car.y, tf);
          const isSelected = selectedSet.has(car.code);

          hitTargets.push({ code: car.code, sx, sy, r: 13 });

          if (car.isOut) {
            ctx.save();
            ctx.globalAlpha = 0.28;
            ctx.beginPath();
            ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.stroke();
            ctx.restore();
            continue;
          }

          ctx.save();
          if (car.inPit) {
            ctx.globalAlpha = 0.62;
          }

          // DRS active outer emerald pulse
          if (car.drsActive) {
            ctx.beginPath();
            ctx.arc(sx, sy, isSelected ? 12 : 9.5, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(0, 230, 118, 0.75)";
            ctx.lineWidth = 2;
            ctx.stroke();
          }

          // Selected driver highlight halo
          if (isSelected) {
            const pulse = 1 + 0.12 * Math.sin(now / 180);
            ctx.beginPath();
            ctx.arc(sx, sy, 12.5 * pulse, 0, Math.PI * 2);
            ctx.fillStyle = `${color}33`;
            ctx.fill();
            ctx.strokeStyle = "#FFFFFF";
            ctx.lineWidth = 2;
            ctx.stroke();
          }

          // Car dot
          const radius = isSelected ? 7.2 : car.position === 1 ? 6.6 : 5.8;
          ctx.beginPath();
          ctx.arc(sx, sy, radius, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.lineWidth = 1.4;
          ctx.strokeStyle = "#090B10";
          ctx.stroke();

          // Driver code tag (shown if labels enabled OR driver is selected)
          if (store.showDriverLabels || isSelected) {
            const label = car.code;
            ctx.font = isSelected
              ? "700 11px 'JetBrains Mono', monospace"
              : "600 10px 'JetBrains Mono', monospace";
            const textW = ctx.measureText(label).width;
            const lx = sx + radius + 5;
            const ly = sy - 7;

            ctx.fillStyle = isSelected
              ? "rgba(12, 15, 22, 0.92)"
              : "rgba(12, 15, 22, 0.74)";
            ctx.beginPath();
            ctx.roundRect(lx - 3, ly - 2, textW + 6, 14, 3);
            ctx.fill();

            if (isSelected) {
              ctx.strokeStyle = color;
              ctx.lineWidth = 1;
              ctx.stroke();
            }

            ctx.fillStyle = isSelected ? "#FFFFFF" : "#E2E8F0";
            ctx.textBaseline = "top";
            ctx.fillText(label, lx, ly);
          }

          ctx.restore();
        }

        // Draw Simulated Safety Car on top if active
        if (snap.safetyCar && snap.safetyCar.alpha > 0.02) {
          const sc = snap.safetyCar;
          const [scX, scY] = worldToScreen(sc.x, sc.y, tf);
          const isPulsing = sc.phase === "deploying" || sc.phase === "returning";
          const pulseScale = isPulsing ? 1 + 0.22 * Math.sin(now / 140) : 1.05;

          ctx.save();
          ctx.globalAlpha = Math.max(0.15, Math.min(1, sc.alpha));

          // Amber beacon glow
          ctx.beginPath();
          ctx.arc(scX, scY, 15 * pulseScale, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(245, 158, 11, 0.28)";
          ctx.fill();

          ctx.beginPath();
          ctx.arc(scX, scY, 8.5, 0, Math.PI * 2);
          ctx.fillStyle = "#F59E0B";
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.strokeStyle = "#FEF3C7";
          ctx.stroke();

          const scLabel =
            sc.phase === "deploying"
              ? "SC DEPLOYING"
              : sc.phase === "returning"
                ? "SC IN"
                : "SC";
          ctx.font = "700 10.5px 'JetBrains Mono', monospace";
          const tw = ctx.measureText(scLabel).width;
          ctx.fillStyle = "rgba(245, 158, 11, 0.95)";
          ctx.beginPath();
          ctx.roundRect(scX + 11, scY - 8, tw + 8, 16, 3);
          ctx.fill();

          ctx.fillStyle = "#090B10";
          ctx.textBaseline = "top";
          ctx.fillText(scLabel, scX + 15, scY - 6);
          ctx.restore();
        }

        carHitTargetsRef.current = hitTargets;
      }

      ctx.restore();
      rafId = requestAnimationFrame(renderFrame);
    };

    rafId = requestAnimationFrame(renderFrame);

    return () => {
      cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Reverse iterate so topmost drawn car wins hit-test
    const targets = carHitTargetsRef.current;
    for (let i = targets.length - 1; i >= 0; i--) {
      const t = targets[i];
      if (Math.hypot(mx - t.sx, my - t.sy) <= t.r) {
        useReplayStore.getState().selectDriver(t.code, e.shiftKey || e.metaKey);
        return;
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full select-none overflow-hidden"
    >
      <canvas
        ref={canvasRef}
        onClick={handleCanvasClick}
        className="block h-full w-full cursor-crosshair"
      />
    </div>
  );
};
