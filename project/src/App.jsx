// Top-level app — stitches it all together.

const { DRIVERS, TEAMS, CIRCUIT, computeStandings, telemetryFor } = window.APEX;
const { buildHotkeyHandler } = window.APEX_HOTKEY;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#FF1E00",
  "density": "engineer",
  "tiltDefault": 62,
  "rotateDefault": -18
}/*EDITMODE-END*/;

function fmtClock(secs) {
  if (typeof secs === "string") return secs;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
}

function fmtRcTime(secs) {
  if (secs == null) return "";
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${String(m).padStart(2,"0")}:${String(s).padStart(6,"0")}`;
}

function App() {
  // Live data from WS
  const { frame, rc, playback, snapshot, trackStatuses } = window.LIVE.useLive();

  // Server-authoritative state
  // t must be 0–1 fraction for Timeline scrub bar; backend sends total_frames
  const totalFrames = frame?.total_frames ?? snapshot?.total_frames ?? 1;
  const t = frame?.frame_index != null ? frame.frame_index / Math.max(totalFrames - 1, 1) : 0;
  const tSeconds = frame?.t_seconds ?? frame?.t ?? 0;
  const totalLaps = frame?.total_laps ?? snapshot?.total_laps ?? 1;
  const lap = frame?.lap ?? 1;
  const clock = frame?.clock ?? "00:00:00";
  const flagState = frame?.flag_state ?? "green";
  const weatherRaw = frame?.weather ?? {};
  const weather = {
    air: Math.round(weatherRaw.air_temp ?? 0),
    track: Math.round(weatherRaw.track_temp ?? 0),
    hum: Math.round(weatherRaw.humidity ?? 0),
  };
  const isPaused = playback?.is_paused ?? true;
  const speed = playback?.speed ?? 1;

  // Session info from snapshot
  const ev = snapshot?.event;
  const SESSION = {
    event: ev ? `R${ev.round} · ${ev.event_name}` : "LOADING...",
    name: "RACE",
    circuit: ev ? [ev.circuit_name, snapshot?.geometry?.total_length_m ? (snapshot.geometry.total_length_m / 1000).toFixed(3) + "KM" : ""].filter(Boolean).join(" · ") : "",
  };

  // Selections
  const [pinned, setPinned] = React.useState(null);
  const [secondary, setSecondary] = React.useState(null);

  // Auto-pin leader on first frame
  React.useEffect(() => {
    if (pinned || !frame?.standings?.length) return;
    setPinned(frame.standings[0].code);
  }, [frame?.standings, pinned]);

  // Camera
  const [rotateX, setRotateX] = React.useState(TWEAK_DEFAULTS.tiltDefault);
  const [rotateZ, setRotateZ] = React.useState(TWEAK_DEFAULTS.rotateDefault);
  const [zoom, setZoom] = React.useState(1);

  // Toggles
  const [showDRS, setShowDRS] = React.useState(true);
  const [showLabels, setShowLabels] = React.useState(true);
  const [showProgress, setShowProgress] = React.useState(true);
  const [compareChannel, setCompareChannel] = React.useState("speed");

  // Tweaks
  const [tweaksOn, setTweaksOn] = React.useState(false);
  const [accent, setAccent] = React.useState(TWEAK_DEFAULTS.accent);

  // Playback controls → POST to server
  const togglePlay = () => {
    if (isPaused) window.APEX_CLIENT.post("/api/playback/play");
    else window.APEX_CLIENT.post("/api/playback/pause");
  };
  const setSpeedRemote = (s) => {
    window.APEX_CLIENT.post("/api/playback/speed", { speed: s });
  };
  const seekRemote = (tVal) => {
    window.APEX_CLIENT.post("/api/playback/seek", { t: tVal });
  };

  // Refs for stable hotkey handler (avoids re-subscribing every frame)
  const tRef = React.useRef(t);
  const speedRef = React.useRef(speed);
  const isPausedRef = React.useRef(isPaused);
  React.useEffect(() => { tRef.current = t; }, [t]);
  React.useEffect(() => { speedRef.current = speed; }, [speed]);
  React.useEffect(() => { isPausedRef.current = isPaused; }, [isPaused]);

  // Hotkeys — listener registered once, reads from refs
  React.useEffect(() => {
    const onKey = buildHotkeyHandler(
      { t: tRef, speed: speedRef, isPaused: isPausedRef },
      window.APEX_CLIENT.post.bind(window.APEX_CLIENT),
      togglePlay,
      seekRemote,
      setSpeedRemote,
      setShowDRS,
      setShowLabels,
      setShowProgress,
    );
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Tweaks protocol
  React.useEffect(() => {
    const onMsg = (e) => {
      if (!e.data || typeof e.data !== "object") return;
      if (e.data.type === "__activate_edit_mode")   setTweaksOn(true);
      if (e.data.type === "__deactivate_edit_mode") setTweaksOn(false);
    };
    window.addEventListener("message", onMsg);
    window.parent.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // Compute race state from live frame
  const standings = React.useMemo(() => computeStandings(t, lap, totalLaps), [frame]);
  const bestLapCode = standings.length > 0
    ? standings.reduce((a, b) => ((a.lastLap ?? Infinity) < (b.lastLap ?? Infinity) ? a : b)).driver.code
    : null;

  // Playhead within lap: use pinned driver's true fraction from backend,
  // which correctly handles SC/pit laps (unlike t * totalLaps % 1).
  const tWithinLap = React.useMemo(() => {
    if (pinned) {
      const entry = standings.find(s => s.driver.code === pinned);
      if (entry?.fraction != null) return entry.fraction % 1;
    }
    return totalLaps > 0 ? (t * totalLaps) % 1 : 0;
  }, [standings, pinned, t, totalLaps]);

  // Safety car events for Timeline: convert track_statuses to {start, end} fractions
  const SC_LABELS = new Set(["sc", "vsc", "red"]);
  const totalDurationS = snapshot?.total_duration_s || 0;
  const safetyCarEvents = React.useMemo(() => {
    if (!trackStatuses?.length || totalDurationS <= 0) return [];
    return trackStatuses
      .filter((e) => SC_LABELS.has(e.status))
      .map((e) => ({
        start: e.start_time / totalDurationS,
        end: (e.end_time ?? totalDurationS) / totalDurationS,
      }));
  }, [trackStatuses, totalDurationS]);

  // Safety car from live frame — project world coords to nearest CIRCUIT index
  let safetyCar = null;
  const scData = frame?.safety_car;
  if (scData) {
    const n = CIRCUIT.length;
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < n; i++) {
      const dx = CIRCUIT[i].x - (scData.x || 0);
      const dy = CIRCUIT[i].y - (scData.y || 0);
      const d2 = dx * dx + dy * dy;
      if (d2 < bestDist) { bestDist = d2; bestIdx = i; }
    }
    safetyCar = { trackIdx: bestIdx, phase: scData.phase || "on_track", alpha: scData.alpha ?? 1, pulse: tSeconds * 60 };
  }

  // Race control feed from WS
  const FEED = (rc || []).map((m) => {
    const cat = (m.category || "").toUpperCase();
    const flag = (m.flag || "").toUpperCase();
    let tag = "INFO";
    if (cat.includes("FLAG") || flag.includes("YELLOW") || flag.includes("RED") || flag.includes("BLACK")) tag = "FLAG";
    if (cat.includes("SAFETY") || flag.includes("SC")) tag = "SC";
    if (cat.includes("DRS")) tag = "DRS";
    return {
      time: fmtRcTime(m.time),
      tag,
      msg: m.message || "",
    };
  });

  const primaryData = telemetryFor(pinned, t);
  const secondaryData = secondary ? telemetryFor(secondary, t) : null;

  const onPick = (code) => {
    if (code === pinned) { setPinned(secondary); setSecondary(null); }
    else setPinned(code);
  };
  const onShiftPick = (code) => {
    if (code === pinned) return;
    if (code === secondary) setSecondary(null);
    else setSecondary(code);
  };

  return (
    <div style={{ position: "fixed", inset: 0, display: "grid", gridTemplateRows: "auto 1fr auto" }}>
      <TopBar
        session={SESSION}
        lap={lap} totalLaps={totalLaps}
        clock={clock}
        weather={weather}
        flagState={flagState}
        safetyCar={!!safetyCar}
      />

      {/* Main layout */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "320px 1fr 360px",
        gap: 10, padding: 10,
        minHeight: 0,
      }}>
        {/* Left: leaderboard */}
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <Leaderboard
            standings={standings}
            pinned={pinned}
            secondary={secondary}
            onPick={onPick}
            onShiftPick={onShiftPick}
            bestLapCode={bestLapCode}
          />
        </div>

        {/* Center: track + bottom panels */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
          {/* Track */}
          <div className="scanline" style={{
            flex: 1, position: "relative",
            background: "linear-gradient(180deg, #0E0E16, #05050A)",
            border: "1px solid rgba(255,255,255,0.06)",
            overflow: "hidden",
            minHeight: 0,
          }}>
            {/* Corner HUD (top-left) */}
            <div style={{
              position: "absolute", top: 12, left: 12,
              display: "flex", flexDirection: "column", gap: 2,
              fontFamily: "JetBrains Mono, monospace",
              zIndex: 3,
            }}>
              <div style={{ fontSize: 9, color: "rgba(180,180,200,0.55)", letterSpacing: "0.2em" }}>
                CIRCUIT VIEW · ISO
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 24, fontWeight: 800, color: "#F6F6FA", letterSpacing: "-0.02em" }}>
                  {ev?.circuit_name?.toUpperCase() || "CIRCUIT"}
                </div>
                <div style={{ fontSize: 9, color: "#FF1E00", letterSpacing: "0.18em", padding: "2px 5px", border: "1px solid #FF1E00" }}>
                  CW
                </div>
              </div>
              <div style={{ fontSize: 10, color: "rgba(180,180,200,0.55)", letterSpacing: "0.1em" }}>
                {snapshot?.geometry?.total_length_m ? `${(snapshot.geometry.total_length_m / 1000).toFixed(3)}KM` : ""}{window.APEX.DRS_ZONES?.length ? ` · ${window.APEX.DRS_ZONES.length} DRS` : ""}
              </div>
            </div>

            {/* Top-right HUD */}
            <div style={{
              position: "absolute", top: 12, right: 12,
              display: "flex", flexDirection: "column", gap: 8,
              zIndex: 3,
            }}>
              <CameraControls
                rotateX={rotateX} setRotateX={setRotateX}
                rotateZ={rotateZ} setRotateZ={setRotateZ}
                zoom={zoom} setZoom={setZoom}
                showDRS={showDRS} setShowDRS={setShowDRS}
                showLabels={showLabels} setShowLabels={setShowLabels}
                showProgress={showProgress} setShowProgress={setShowProgress}
              />
            </div>

            {/* Corner ticks */}
            {["tl","tr","bl","br"].map((p) => (
              <div key={p} style={{
                position: "absolute", width: 16, height: 16, zIndex: 3,
                borderColor: "rgba(255,30,0,0.5)",
                borderStyle: "solid", borderWidth: 0,
                ...(p === "tl" ? { top: 4, left: 4,  borderTopWidth: 1, borderLeftWidth: 1 } :
                   p === "tr" ? { top: 4, right: 4, borderTopWidth: 1, borderRightWidth: 1 } :
                   p === "bl" ? { bottom: 4, left: 4, borderBottomWidth: 1, borderLeftWidth: 1 } :
                                { bottom: 4, right: 4, borderBottomWidth: 1, borderRightWidth: 1 }),
              }}/>
            ))}

            <IsoTrack
              standings={standings}
              safetyCar={safetyCar}
              pinned={pinned}
              secondary={secondary}
              onPickDriver={(code, e) => {
                if (e && e.shiftKey) onShiftPick(code);
                else onPick(code);
              }}
              showDRS={showDRS}
              showLabels={showLabels}
              rotateX={rotateX}
              rotateZ={rotateZ}
              zoom={zoom}
            />

            {/* Bottom HUD: selected driver pip + compare toggle */}
            {pinned && (
              <div style={{
                position: "absolute", bottom: 12, left: 12,
                fontFamily: "JetBrains Mono, monospace",
                display: "flex", alignItems: "center", gap: 10,
                padding: "6px 10px",
                background: "rgba(11,11,17,0.8)",
                border: "1px solid rgba(255,30,0,0.3)",
                zIndex: 3,
              }}>
                <div style={{ width: 6, height: 6, background: "#FF1E00", boxShadow: "0 0 6px #FF1E00" }}/>
                <div style={{ fontSize: 10, color: "rgba(180,180,200,0.6)", letterSpacing: "0.14em" }}>PINNED</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#F6F6FA" }}>{pinned}</div>
                {secondary && (
                  <React.Fragment>
                    <div style={{ width: 1, height: 12, background: "rgba(255,255,255,0.1)" }}/>
                    <div style={{ width: 6, height: 6, background: "#00D9FF", boxShadow: "0 0 6px #00D9FF" }}/>
                    <div style={{ fontSize: 10, color: "rgba(180,180,200,0.6)", letterSpacing: "0.14em" }}>COMPARE</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#F6F6FA" }}>{secondary}</div>
                  </React.Fragment>
                )}
                <div style={{ fontSize: 9, color: "rgba(180,180,200,0.45)", letterSpacing: "0.1em", paddingLeft: 10 }}>
                  CLICK · PIN ·  SHIFT+CLICK · COMPARE
                </div>
              </div>
            )}

            {/* Bottom HUD: scan indicator */}
            <div style={{
              position: "absolute", bottom: 12, right: 12,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9, color: "rgba(180,180,200,0.55)",
              letterSpacing: "0.14em", zIndex: 3,
              display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2,
            }}>
              <div>TELEMETRY · 240Hz</div>
              <div style={{ color: "#1EFF6A" }}>● LIVE · SECTOR {t < 0.33 ? 1 : t < 0.66 ? 2 : 3}</div>
            </div>
          </div>

          {/* Bottom strip: strategy + compare + feed */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1.4fr 1fr",
            gap: 10,
            height: 260,
            minHeight: 0,
          }}>
            <StrategyStrip standings={standings} totalLaps={totalLaps} lap={lap}/>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
              <CompareTraces pinned={pinned} secondary={secondary} lap={lap} channel={compareChannel} setChannel={setCompareChannel} tWithinLap={tWithinLap}/>
              <SectorTimes pinned={pinned} secondary={secondary} lap={lap} standings={standings}/>
            </div>
            <RaceFeed events={FEED}/>
          </div>
        </div>

        {/* Right: driver panels */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 0, overflow: "auto" }}>
          <DriverCard code={pinned} data={primaryData} accent="#FF1E00" standings={standings}/>
          {secondary
            ? <DriverCard code={secondary} data={secondaryData} accent="#00D9FF" secondary standings={standings}/>
            : <div style={{
                padding: 14,
                border: "1px dashed rgba(0,217,255,0.2)",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9, color: "rgba(180,180,200,0.45)",
                letterSpacing: "0.12em", textAlign: "center",
              }}>
                SHIFT + CLICK DRIVER TO COMPARE
              </div>
          }
          <GapViz standings={standings} pinned={pinned}/>
        </div>
      </div>

      <Timeline
        t={t} setT={seekRemote}
        playing={!isPaused} setPlaying={togglePlay}
        speed={speed} setSpeed={setSpeedRemote}
        lap={lap} totalLaps={totalLaps}
        safetyCarEvents={safetyCarEvents}
      />

      {tweaksOn && <TweaksPanel accent={accent} setAccent={setAccent} rotateX={rotateX} setRotateX={setRotateX} rotateZ={rotateZ} setRotateZ={setRotateZ} zoom={zoom} setZoom={setZoom}/>}
    </div>
  );
}

function TweaksPanel({ accent, setAccent, rotateX, setRotateX, rotateZ, setRotateZ, zoom, setZoom }) {
  const presets = [
    { name: "BROADCAST", rx: 62, rz: -18, z: 1 },
    { name: "TOP DOWN",  rx: 0,  rz: 0,   z: 1 },
    { name: "LOW ANGLE", rx: 78, rz: -25, z: 1.15 },
    { name: "PADDOCK",   rx: 70, rz: 45,  z: 0.9 },
  ];
  return (
    <div style={{
      position: "fixed", bottom: 86, right: 14,
      width: 260,
      background: "linear-gradient(180deg, rgba(20,20,30,0.96), rgba(11,11,17,0.98))",
      border: "1px solid rgba(255,30,0,0.4)",
      padding: 12,
      fontFamily: "JetBrains Mono, monospace",
      zIndex: 50,
      boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
    }}>
      <div style={{ fontSize: 10, fontWeight: 800, color: "#F6F6FA", letterSpacing: "0.2em", marginBottom: 10 }}>
        TWEAKS
      </div>
      <div style={{ fontSize: 8, color: "rgba(180,180,200,0.55)", letterSpacing: "0.14em", marginBottom: 6 }}>CAMERA PRESETS</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 12 }}>
        {presets.map((p) => (
          <button key={p.name} onClick={() => { setRotateX(p.rx); setRotateZ(p.rz); setZoom(p.z); }} style={{
            padding: "6px 4px", background: "transparent",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#E6E6EF", cursor: "pointer",
            fontFamily: "inherit", fontSize: 9, letterSpacing: "0.14em", fontWeight: 700,
          }}>{p.name}</button>
        ))}
      </div>
      <div style={{ fontSize: 8, color: "rgba(180,180,200,0.55)", letterSpacing: "0.14em", marginBottom: 6 }}>ACCENT</div>
      <div style={{ display: "flex", gap: 4 }}>
        {["#FF1E00", "#FF8A1E", "#C15AFF", "#1EFF6A"].map((c) => (
          <button key={c} onClick={() => setAccent(c)} style={{
            width: 28, height: 22, background: c, border: accent === c ? "2px solid #FFFFFF" : "1px solid rgba(255,255,255,0.1)",
            cursor: "pointer", padding: 0,
          }}/>
        ))}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <window.LIVE.LiveProvider>
    <window.LOADING_GATE>
      <App />
    </window.LOADING_GATE>
  </window.LIVE.LiveProvider>
);
