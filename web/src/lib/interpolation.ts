import {
  ColumnarFrames,
  InterpolatedDriver,
  InterpolatedSafetyCar,
  InterpolatedSnapshot,
  InterpolatedWeather,
  ReplayManifest,
} from "@/types/replay";

export function detectLaunchTimeS(frames: ColumnarFrames): number {
  const n = frames.t.length;
  if (n === 0) return 0;
  const driverList = Object.values(frames.drivers);
  if (driverList.length === 0) return 0;

  const limit = Math.min(n, 400);
  const fastThreshold = Math.min(8, Math.max(3, Math.floor(driverList.length * 0.45)));

  // Find the true field-wide launch where nearly half the grid is > 25 km/h
  let accelIdx = -1;
  for (let i = 0; i < limit; i++) {
    let fastCount = 0;
    for (const drv of driverList) {
      if ((drv.speed[i] ?? 0) >= 25.0) {
        fastCount += 1;
        if (fastCount >= fastThreshold) {
          accelIdx = i;
          break;
        }
      }
    }
    if (accelIdx !== -1) break;
  }

  if (accelIdx === -1) return 0;

  // Walk back to the exact instant the front of the grid started rolling (>= 5 km/h)
  let launchIdx = accelIdx;
  while (launchIdx > 0) {
    let movingCount = 0;
    for (const drv of driverList) {
      if ((drv.speed[launchIdx - 1] ?? 0) >= 5.0) {
        movingCount += 1;
      }
    }
    if (movingCount < 3) break;
    launchIdx -= 1;
  }

  return frames.t[launchIdx];
}

export function formatRaceClock(seconds: number): string {
  const clamped = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(clamped / 3600);
  const mins = Math.floor((clamped % 3600) / 60);
  const secs = clamped % 60;
  return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export function formatCompassDirection(deg: number | null): string {
  if (deg === null || Number.isNaN(deg)) return "—";
  const dirs = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ];
  const norm = ((deg % 360) + 360) % 360;
  return dirs[Math.round(norm / 22.5) % 16];
}

export function getTyreMeta(compoundInt: number): {
  short: string;
  name: string;
  color: string;
  textColor: string;
} {
  switch (compoundInt) {
    case 0:
      return { short: "S", name: "SOFT", color: "#FF3B30", textColor: "#FFFFFF" };
    case 1:
      return { short: "M", name: "MEDIUM", color: "#FFD60A", textColor: "#0B0D12" };
    case 2:
      return { short: "H", name: "HARD", color: "#F2F2F7", textColor: "#0B0D12" };
    case 3:
      return { short: "I", name: "INTER", color: "#30D158", textColor: "#0B0D12" };
    case 4:
      return { short: "W", name: "WET", color: "#0A84FF", textColor: "#FFFFFF" };
    default:
      return { short: "?", name: "UNKNOWN", color: "#6B7280", textColor: "#FFFFFF" };
  }
}

export function getTrackStatusMeta(code: string): {
  key: "GREEN" | "YELLOW" | "SC" | "VSC" | "RED";
  label: string;
  trackStroke: string;
  badgeBg: string;
  badgeText: string;
} {
  switch (String(code)) {
    case "2":
      return {
        key: "YELLOW",
        label: "YELLOW FLAG",
        trackStroke: "#FACC15",
        badgeBg: "rgba(250, 204, 21, 0.18)",
        badgeText: "#FDE047",
      };
    case "4":
      return {
        key: "SC",
        label: "SAFETY CAR",
        trackStroke: "#F59E0B",
        badgeBg: "rgba(245, 158, 11, 0.22)",
        badgeText: "#FCD34D",
      };
    case "5":
      return {
        key: "RED",
        label: "RED FLAG",
        trackStroke: "#EF4444",
        badgeBg: "rgba(239, 68, 68, 0.24)",
        badgeText: "#FCA5A5",
      };
    case "6":
    case "7":
      return {
        key: "VSC",
        label: code === "7" ? "VSC ENDING" : "VIRTUAL SAFETY CAR",
        trackStroke: "#FB923C",
        badgeBg: "rgba(251, 146, 60, 0.20)",
        badgeText: "#FDBA74",
      };
    default:
      return {
        key: "GREEN",
        label: "TRACK CLEAR",
        trackStroke: "#6E7686",
        badgeBg: "rgba(16, 185, 129, 0.14)",
        badgeText: "#34D399",
      };
  }
}

function findFrameBracket(times: number[], targetT: number): [number, number, number] {
  const n = times.length;
  if (n === 0) return [0, 0, 0];
  if (targetT <= times[0]) return [0, 0, 0];
  if (targetT >= times[n - 1]) return [n - 1, n - 1, 0];

  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= targetT) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  const dt = times[hi] - times[lo];
  const alpha = dt > 1e-6 ? (targetT - times[lo]) / dt : 0;
  return [lo, hi, Math.max(0, Math.min(1, alpha))];
}

function lerpSafe(v0: number, v1: number, alpha: number, maxJump = Infinity): number {
  if (Math.abs(v1 - v0) > maxJump) {
    return alpha < 0.5 ? v0 : v1;
  }
  return v0 + (v1 - v0) * alpha;
}

export function sampleSnapshotAtTime(
  manifest: ReplayManifest,
  frames: ColumnarFrames,
  timeS: number
): InterpolatedSnapshot {
  const [i0, i1, alpha] = findFrameBracket(frames.t, timeS);
  const clampedT = frames.t.length > 0 ? lerpSafe(frames.t[i0], frames.t[i1], alpha) : 0;

  // Determine active track status
  let trackStatusCode = "1";
  for (const st of manifest.track_statuses) {
    if (
      clampedT >= st.start_time &&
      (st.end_time === null || clampedT < st.end_time)
    ) {
      trackStatusCode = String(st.status);
      break;
    }
  }

  const circuitLen = manifest.session_info.circuit_length_m || 5200;
  const rawList: InterpolatedDriver[] = [];

  for (const [code, series] of Object.entries(frames.drivers)) {
    if (!series.x || series.x.length === 0) continue;

    const x0 = series.x[i0];
    const y0 = series.y[i0];
    const x1 = series.x[i1];
    const y1 = series.y[i1];

    // Prevent infield teleports if telemetry had a dropout jump > 450m
    const jumpDist = Math.hypot(x1 - x0, y1 - y0);
    const x = jumpDist > 450 ? (alpha < 0.5 ? x0 : x1) : x0 + (x1 - x0) * alpha;
    const y = jumpDist > 450 ? (alpha < 0.5 ? y0 : y1) : y0 + (y1 - y0) * alpha;

    const dist = lerpSafe(series.dist[i0], series.dist[i1], alpha, 800);
    const speed = lerpSafe(series.speed[i0], series.speed[i1], alpha);
    const throttle = lerpSafe(series.throttle[i0], series.throttle[i1], alpha);
    const brake = lerpSafe(series.brake[i0], series.brake[i1], alpha);

    const nearIdx = alpha < 0.5 ? i0 : i1;
    const isOut = series.is_out[nearIdx] === 1;
    const inPit = !isOut && series.in_pit[nearIdx] === 1;
    const drsCode = series.drs[nearIdx];

    rawList.push({
      code,
      x,
      y,
      dist,
      rel_dist: series.rel_dist[nearIdx],
      lap: series.lap[nearIdx],
      position: series.pos[nearIdx],
      tyre: series.tyre[nearIdx],
      tyre_life: series.tyre_life[nearIdx],
      speed,
      gear: series.gear[nearIdx],
      drsActive: drsCode === 10 || drsCode === 12 || drsCode === 14,
      throttle,
      brake,
      inPit,
      isOut,
      gapToLeader: "",
      intervalAhead: "",
    });
  }

  // Order active drivers ahead of retired drivers, then by frame position / race distance
  rawList.sort((a, b) => {
    if (a.isOut !== b.isOut) return a.isOut ? 1 : -1;
    if (a.position !== b.position) return a.position - b.position;
    return b.dist - a.dist;
  });

  const leader = rawList[0];
  const driversByCode: Record<string, InterpolatedDriver> = {};
  const isPreStart =
    Boolean(leader) &&
    leader.lap <= 1 &&
    leader.dist <= 5 &&
    rawList.every((d) => d.isOut || d.speed < 5);

  rawList.forEach((drv, idx) => {
    drv.position = idx + 1;
    if (drv.isOut) {
      drv.gapToLeader = "OUT";
      drv.intervalAhead = "OUT";
    } else if (isPreStart) {
      drv.gapToLeader = idx === 0 ? "0.0s" : "+0.0s";
      drv.intervalAhead = idx === 0 ? "0.0s" : "+0.0s";
    } else if (idx === 0) {
      drv.gapToLeader = "LEADER";
      drv.intervalAhead = "LEADER";
    } else if (leader) {
      const distBehindLeader = Math.max(0, leader.dist - drv.dist);
      const lapsDown = Math.floor(distBehindLeader / circuitLen);
      // Estimate gap using a realistic mean lap speed (~55 m/s ≈ 198 km/h) blended with current speed
      const refMps = Math.max(46, Math.min(72, (drv.speed + leader.speed) * 0.5 / 3.6 || 55));
      if (lapsDown >= 1 && leader.lap - drv.lap >= 1) {
        const lapDiff = Math.max(1, leader.lap - drv.lap);
        drv.gapToLeader = `+${lapDiff}L`;
      } else {
        const gapSec = distBehindLeader / refMps;
        drv.gapToLeader = `+${gapSec.toFixed(1)}s`;
      }

      const ahead = rawList[idx - 1];
      const distBehindAhead = Math.max(0, ahead.dist - drv.dist);
      const intSec = distBehindAhead / refMps;
      drv.intervalAhead = distBehindAhead > circuitLen ? `+1L` : `+${intSec.toFixed(1)}s`;
    }
    driversByCode[drv.code] = drv;
  });

  // Safety Car interpolation
  let safetyCar: InterpolatedSafetyCar | null = null;
  const sc = frames.safety_car;
  if (sc && (sc.active[i0] === 1 || sc.active[i1] === 1)) {
    let scX = sc.x[i0];
    let scY = sc.y[i0];
    if (sc.active[i0] === 1 && sc.active[i1] === 1) {
      const scJump = Math.hypot(sc.x[i1] - sc.x[i0], sc.y[i1] - sc.y[i0]);
      scX = scJump > 450 ? sc.x[i0] : sc.x[i0] + (sc.x[i1] - sc.x[i0]) * alpha;
      scY = scJump > 450 ? sc.y[i0] : sc.y[i0] + (sc.y[i1] - sc.y[i0]) * alpha;
    } else if (sc.active[i1] === 1) {
      scX = sc.x[i1];
      scY = sc.y[i1];
    }
    const nearSc = sc.active[i0] === 1 ? i0 : i1;
    safetyCar = {
      x: scX,
      y: scY,
      phase: sc.phase[nearSc] || "on_track",
      alpha: lerpSafe(sc.alpha[i0], sc.alpha[i1], alpha),
    };
  }

  // Weather snapshot
  let weather: InterpolatedWeather | null = null;
  if (frames.weather) {
    const nearW = alpha < 0.5 ? i0 : i1;
    weather = {
      trackTemp: frames.weather.track_temp[nearW],
      airTemp: frames.weather.air_temp[nearW],
      humidity: frames.weather.humidity[nearW],
      windSpeed: frames.weather.wind_speed[nearW],
      windDirection: frames.weather.wind_direction[nearW],
      isRaining: frames.weather.rain[nearW] === 1,
    };
  }

  // Collect Race Control messages up to current time (newest first)
  const recentMessages = [];
  const rcList = manifest.race_control_messages || [];
  for (let i = rcList.length - 1; i >= 0; i--) {
    if (rcList[i].time <= clampedT) {
      recentMessages.push(rcList[i]);
      if (recentMessages.length >= 25) break;
    }
  }

  return {
    timeS: clampedT,
    formattedTime: formatRaceClock(clampedT),
    leaderLap: leader ? leader.lap : frames.lap[i0] || 1,
    leaderCode: leader ? leader.code : "",
    trackStatusCode,
    driversSorted: rawList,
    driversByCode,
    safetyCar,
    weather,
    recentMessages,
  };
}
