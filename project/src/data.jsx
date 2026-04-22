// Live data shim — populates window.APEX from the backend.
// Async bootstrap fetches CIRCUIT/TEAMS/DRIVERS without blocking paint.
// Fallbacks are installed immediately so components can destructure safely;
// real data mutates the same objects in-place once fetched.

const BASE = `${location.protocol}//${location.host}`;

async function asyncFetch(path) {
  try {
    const r = await fetch(BASE + path);
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

// --- Compound int → APEX key mapping ---
const COMPOUND_MAP = { 0: "S", 1: "M", 2: "H", 3: "I", 4: "W" };

// --- TEAMS (mutable — colors updated from WS snapshot) ---
const TEAMS = {};
const DRIVERS = [];

// --- CIRCUIT / SECTORS / DRS_ZONES (const arrays, mutated in-place) ---
const CIRCUIT = [{ x: 0, y: 0 }];
const SECTORS = [
  { idx: 0, color: "#FF1E00", name: "S1" },
  { idx: 0, color: "#FFD93A", name: "S2" },
  { idx: 0, color: "#00D9FF", name: "S3" },
];
const DRS_ZONES = [];

// --- Populate from summary / geometry (async, non-blocking) ---
let _dataResolved;
const APEX_DATA_READY = new Promise((resolve) => { _dataResolved = resolve; });

async function _initAPEX() {
  const [_summary, _geometry] = await Promise.all([
    asyncFetch("/api/session/summary"),
    asyncFetch("/api/session/geometry"),
  ]);

  if (_summary && _summary.drivers) {
    const teamsSeen = {};
    for (const d of _summary.drivers) {
      const teamKey = d.team || "Unknown";
      if (!teamsSeen[teamKey]) {
        teamsSeen[teamKey] = true;
        TEAMS[teamKey] = { name: teamKey, color: "#FF1E00", sub: "#8A0A00" };
      }
      DRIVERS.push({
        code: d.code,
        num: d.number || 0,
        name: d.full_name || d.code,
        team: teamKey,
        country: d.country || "",
      });
    }
  }

  if (_geometry) {
    const cx = _geometry.centerline?.x || [];
    const cy = _geometry.centerline?.y || [];
    CIRCUIT.splice(0, CIRCUIT.length, ...cx.map((x, i) => ({ x, y: cy[i] || 0 })));

    DRS_ZONES.splice(0, DRS_ZONES.length, ...(_geometry.drs_zones || []).map(z => ({
      start: z.start_idx,
      end: z.end_idx,
    })));

    const totalLength = _geometry.total_length_m || 1;
    const n = CIRCUIT.length;
    const boundaries = _geometry.sector_boundaries_m || [];
    const sectorColors = ["#FF1E00", "#FFD93A", "#00D9FF"];

    if (boundaries.length >= 2) {
      SECTORS.splice(0, SECTORS.length,
        { idx: 0, color: sectorColors[0], name: "S1" },
        ...boundaries.slice(0, 2).map((m, i) => ({
          idx: Math.round((m / totalLength) * (n - 1)) % n,
          color: sectorColors[i + 1] || "#FFFFFF",
          name: `S${i + 2}`,
        })),
      );
    } else if (n > 1) {
      SECTORS.splice(0, SECTORS.length,
        { idx: 0, color: "#FF1E00", name: "S1" },
        { idx: Math.floor(n / 3), color: "#FFD93A", name: "S2" },
        { idx: Math.floor(2 * n / 3), color: "#00D9FF", name: "S3" },
      );
    }
  }

  // Fallbacks (only fill if still empty after fetch)
  if (CIRCUIT.length === 0) CIRCUIT.push({ x: 0, y: 0 });
  if (DRIVERS.length === 0) {
    DRIVERS.push({ code: "???", num: 0, name: "Loading...", team: "Loading", country: "" });
    TEAMS["Loading"] = { name: "Loading", color: "#FF1E00", sub: "#8A0A00" };
  }
  if (SECTORS.length === 0) {
    SECTORS.push(
      { idx: 0, color: "#FF1E00", name: "S1" },
      { idx: Math.floor(CIRCUIT.length / 3), color: "#FFD93A", name: "S2" },
      { idx: Math.floor(2 * CIRCUIT.length / 3), color: "#00D9FF", name: "S3" },
    );
  }

  _dataResolved();
}

_initAPEX();


const COMPOUNDS = {
  S:  { label: "SOFT",   color: "#FF3A3A" },
  M:  { label: "MEDIUM", color: "#FFD93A" },
  H:  { label: "HARD",   color: "#F4F4F4" },
  I:  { label: "INTER",  color: "#3AE87A" },
  W:  { label: "WET",    color: "#3A9BFF" },
};

// --- Live frame storage (written by live_state.jsx) ---
window.__LIVE_FRAME = null;

// --- Snapshot installer (called from live_state.jsx on WS snapshot) ---
function _installSnapshot(snap) {
  if (!snap) return;
  const meta = snap.driver_meta || {};
  // Clear sentinel "???" entry on first real snapshot
  if (Object.keys(meta).length > 0) {
    const sentinelIdx = DRIVERS.findIndex(d => d.code === "???");
    if (sentinelIdx !== -1) DRIVERS.splice(sentinelIdx, 1);
    delete TEAMS["Loading"];
  }
  const colors = snap.driver_colors || {};
  for (const [code, info] of Object.entries(meta)) {
    const teamKey = info.team;
    if (TEAMS[teamKey] && colors[code]) {
      TEAMS[teamKey].color = colors[code];
    }
    if (!TEAMS[teamKey] && teamKey) {
      TEAMS[teamKey] = { name: teamKey, color: colors[code] || "#FF1E00", sub: "#8A0A00" };
    }
  }
  // Update driver details from snapshot meta
  for (const [code, info] of Object.entries(meta)) {
    const existing = DRIVERS.find(d => d.code === code);
    if (existing) {
      if (info.full_name) existing.name = info.full_name;
      if (info.country) existing.country = info.country;
    } else {
      DRIVERS.push({
        code: info.code || code,
        num: info.number || 0,
        name: info.full_name || code,
        team: info.team || "Unknown",
        country: info.country || "",
      });
    }
  }
  // Rebuild geometry from snapshot if present (mutate in-place)
  const geo = snap.geometry;
  if (geo) {
    const cx = geo.centerline?.x || [];
    const cy = geo.centerline?.y || [];
    if (cx.length > 1) {
      CIRCUIT.splice(0, CIRCUIT.length, ...cx.map((x, i) => ({ x, y: cy[i] || 0 })));
      DRS_ZONES.splice(0, DRS_ZONES.length, ...(geo.drs_zones || []).map(z => ({
        start: z.start_idx,
        end: z.end_idx,
      })));
      const totalLength = geo.total_length_m || 1;
      const n = CIRCUIT.length;
      const boundaries = geo.sector_boundaries_m || [];
      const sectorColors = ["#FF1E00", "#FFD93A", "#00D9FF"];
      if (boundaries.length >= 2) {
        SECTORS.splice(0, SECTORS.length,
          { idx: 0, color: sectorColors[0], name: "S1" },
          ...boundaries.slice(0, 2).map((m, i) => ({
            idx: Math.round((m / totalLength) * (n - 1)) % n,
            color: sectorColors[i + 1] || "#FFFFFF",
            name: `S${i + 2}`,
          })),
        );
      } else if (n > 1) {
        SECTORS.splice(0, SECTORS.length,
          { idx: 0, color: "#FF1E00", name: "S1" },
          { idx: Math.floor(n / 3), color: "#FFD93A", name: "S2" },
          { idx: Math.floor(2 * n / 3), color: "#00D9FF", name: "S3" },
        );
      }
    }
  }
}

// --- computeStandings: transform live frame standings to component format ---
function computeStandings(t, lap, totalLaps) {
  const f = window.__LIVE_FRAME;
  if (!f?.standings) return [];
  const n = CIRCUIT.length;
  return f.standings.map((s) => {
    const d = DRIVERS.find((x) => x.code === s.code) || { code: s.code, num: 0, name: s.code, team: "Unknown", country: "" };
    const perLap = s.fraction != null
      ? s.fraction % 1
      : (s.rel_dist != null && s.rel_dist >= 0 && s.rel_dist <= 1.01 ? s.rel_dist : 0);
    const trackIdx = Math.round(perLap * (n - 1)) % n;
    return {
      pos: s.pos,
      driver: d,
      gap: s.gap_s ?? 0,
      interval: s.interval_s ?? 0,
      trackIdx,
      compound: COMPOUND_MAP[s.compound_int] || "M",
      tyreAge: s.tyre_age_laps ?? 0,
      lastLap: s.last_lap_s ?? 0,
      bestLap: s.best_lap_s ?? 0,
      lastS1: s.last_s1_s ?? null,
      lastS2: s.last_s2_s ?? null,
      lastS3: s.last_s3_s ?? null,
      pbLap: s.personal_best_lap_s ?? null,
      pbS1: s.personal_best_s1_s ?? null,
      pbS2: s.personal_best_s2_s ?? null,
      pbS3: s.personal_best_s3_s ?? null,
      stint: s.stint ?? 1,
      status: s.status || "RUN",
      pit: s.in_pit || false,
      inDRS: s.in_drs || false,
      speedKph: s.speed_kph ?? 0,
      fraction: s.fraction ?? 0,
    };
  }).sort((a, b) => a.pos - b.pos);
}

// --- telemetryFor: extract driver telemetry from live frame ---
function telemetryFor(driverCode, t) {
  const f = window.__LIVE_FRAME;
  if (!f?.standings) return { speed: 0, throttle: 0, brake: 0, gear: 1, rpm: 0, drs: false };
  const s = f.standings.find((x) => x.code === driverCode);
  if (!s) return { speed: 0, throttle: 0, brake: 0, gear: 1, rpm: 0, drs: false };
  return {
    speed: Math.round(s.speed_kph || 0),
    throttle: Math.round(s.throttle_pct || 0),
    brake: Math.round(s.brake_pct || 0),
    gear: s.gear || 1,
    rpm: Math.round(s.rpm || 0),
    drs: s.in_drs || false,
  };
}

// --- Telemetry accumulator: stores real per-lap samples from live frames ---
window.__LAP_TELEMETRY = {};  // { driverCode: { lapNum: [{fraction, speed, throttle, brake, gear, rpm}, ...] } }

function _accumulateFrame(frame) {
  if (!frame?.standings) return;
  for (const s of frame.standings) {
    const code = s.code;
    const lap = s.lap;
    const frac = s.fraction != null ? s.fraction % 1 : (s.rel_dist != null && s.rel_dist >= 0 && s.rel_dist <= 1.01 ? s.rel_dist : 0);
    if (frac == null || frac < 0) continue;

    if (!window.__LAP_TELEMETRY[code]) window.__LAP_TELEMETRY[code] = {};
    if (!window.__LAP_TELEMETRY[code][lap]) window.__LAP_TELEMETRY[code][lap] = [];

    const bucket = window.__LAP_TELEMETRY[code][lap];
    // Skip if fraction hasn't advanced (avoid duplicates)
    const last = bucket[bucket.length - 1];
    if (last && Math.abs(frac - last.fraction) < 0.0005) continue;

    bucket.push({
      fraction: frac,
      speed: s.speed_kph ?? 0,
      throttle: s.throttle_pct ?? 0,
      brake: s.brake_pct ?? 0,
      gear: s.gear ?? 1,
      rpm: s.rpm ?? 0,
    });
  }
}

function lapTrace(driverCode, lap, channel = "speed") {
  const lapData = window.__LAP_TELEMETRY?.[driverCode]?.[lap];
  if (!lapData || lapData.length < 2) return [];

  // Sort by fraction and resample to 200 evenly-spaced points
  const sorted = [...lapData].sort((a, b) => a.fraction - b.fraction);
  const N = 200;
  const out = [];
  for (let i = 0; i < N; i++) {
    const targetFrac = i / (N - 1);
    // Binary-style bracket search
    let lo = 0, hi = sorted.length - 1;
    for (let j = 0; j < sorted.length - 1; j++) {
      if (sorted[j].fraction <= targetFrac && sorted[j + 1].fraction >= targetFrac) {
        lo = j; hi = j + 1; break;
      }
    }
    const sLo = sorted[lo], sHi = sorted[hi];
    const span = sHi.fraction - sLo.fraction;
    const t = span > 0 ? (targetFrac - sLo.fraction) / span : 0;
    out.push(sLo[channel] + t * (sHi[channel] - sLo[channel]));
  }
  return out;
}

function getSessionBest() {
  return window.__LIVE_SNAPSHOT?.session_best || {};
}
function getStints(code) {
  return window.__LIVE_SNAPSHOT?.stints?.[code] || [];
}
function getPitStops(code) {
  return window.__LIVE_SNAPSHOT?.pit_stops?.[code] || [];
}

window.APEX = {
  TEAMS, DRIVERS, COMPOUNDS, CIRCUIT, SECTORS, DRS_ZONES,
  computeStandings, telemetryFor, lapTrace,
  _installSnapshot, _accumulateFrame,
  getSessionBest, getStints, getPitStops,
};
window.APEX_DATA_READY = APEX_DATA_READY;
