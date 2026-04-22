// Top bar, timeline, controls, tweaks.

const { SECTORS } = window.APEX;

function TopBar({ session, lap, totalLaps, clock, weather, flagState, safetyCar }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "auto 1fr auto",
      gap: 16,
      padding: "10px 18px",
      background: "linear-gradient(180deg, rgba(11,11,17,0.98), rgba(11,11,17,0.9))",
      borderBottom: "1px solid rgba(255,30,0,0.25)",
      fontFamily: "JetBrains Mono, monospace",
      alignItems: "center",
      position: "relative",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        {/* Logo mark */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <svg width="22" height="22" viewBox="0 0 22 22">
            <path d="M2 18 L8 4 L14 4 L10 12 L20 12 L18 18 Z" fill="#FF1E00"/>
          </svg>
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, color: "#E6E6EF", letterSpacing: "0.22em" }}>APEX · PITWALL</div>
            <div style={{ fontSize: 8, color: "rgba(180,180,200,0.5)", letterSpacing: "0.2em" }}>RACE ENGINEER CONSOLE</div>
          </div>
        </div>
        <Divider/>
        <MetaItem label="EVENT" value={session.event}/>
        <MetaItem label="SESSION" value={session.name}/>
        <MetaItem label="CIRCUIT" value={session.circuit}/>
      </div>

      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 18 }}>
        <FlagBadge state={flagState} safetyCar={safetyCar}/>
        <BigMeta label="LAP" value={`${String(lap).padStart(2, "0")}/${totalLaps}`} accent="#FF1E00"/>
        <BigMeta label="RACE TIME" value={clock}/>
        <BigMeta label="AIR" value={`${weather.air}°`}/>
        <BigMeta label="TRACK" value={`${weather.track}°`}/>
        <BigMeta label="HUM" value={`${weather.hum}%`}/>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <LiveDot/>
        <div style={{ fontSize: 9, letterSpacing: "0.16em", color: "rgba(180,180,200,0.7)" }}>TELEMETRY STREAM</div>
      </div>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, height: 24, background: "rgba(255,255,255,0.08)" }}/>;
}

function MetaItem({ label, value }) {
  return (
    <div style={{ lineHeight: 1.1 }}>
      <div style={{ fontSize: 8, color: "rgba(180,180,200,0.45)", letterSpacing: "0.18em" }}>{label}</div>
      <div style={{ fontSize: 11, color: "#E6E6EF", fontWeight: 600, letterSpacing: "0.06em" }}>{value}</div>
    </div>
  );
}

function BigMeta({ label, value, accent }) {
  return (
    <div style={{ textAlign: "center", lineHeight: 1.05 }}>
      <div style={{ fontSize: 8, color: "rgba(180,180,200,0.5)", letterSpacing: "0.16em" }}>{label}</div>
      <div style={{ fontSize: 15, color: accent || "#F6F6FA", fontWeight: 700, fontVariantNumeric: "tabular-nums", letterSpacing: "0.02em" }}>{value}</div>
    </div>
  );
}

function LiveDot() {
  return (
    <div style={{ position: "relative", width: 8, height: 8 }}>
      <div style={{ position: "absolute", inset: 0, borderRadius: 4, background: "#1EFF6A" }}/>
      <div style={{ position: "absolute", inset: -3, borderRadius: 7, background: "#1EFF6A", opacity: 0.3, animation: "apexpulse 1.6s infinite" }}/>
    </div>
  );
}

function FlagBadge({ state, safetyCar }) {
  let label = "GREEN", bg = "#1EFF6A", fg = "#0B0B11";
  if (state === "vsc") { label = "VIRTUAL SC"; bg = "#FFB800"; }
  else if (safetyCar || state === "sc") { label = "SAFETY CAR"; bg = "#FFB800"; }
  else if (state === "yellow") { label = "YELLOW"; bg = "#FFD93A"; }
  else if (state === "red") { label = "RED FLAG"; bg = "#FF1E00"; fg = "#FFFFFF"; }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{
        padding: "4px 10px",
        background: bg, color: fg,
        fontSize: 10, fontWeight: 800,
        letterSpacing: "0.18em",
        fontFamily: "JetBrains Mono, monospace",
      }}>
        {label}
      </div>
      {state === "yellow" && safetyCar && (
        <div style={{
          padding: "4px 10px",
          background: "#FFB800", color: "#0B0B11",
          fontSize: 10, fontWeight: 800,
          letterSpacing: "0.18em",
          fontFamily: "JetBrains Mono, monospace",
        }}>
          SC
        </div>
      )}
    </div>
  );
}

// Bottom timeline
function Timeline({ t, setT, playing, setPlaying, speed, setSpeed, lap, totalLaps, safetyCarEvents }) {
  const trackRef = React.useRef(null);
  const [drag, setDrag] = React.useState(false);
  const [scrubT, setScrubT] = React.useState(null);
  const scrubRef = React.useRef(null);
  const setTRef = React.useRef(setT);
  React.useEffect(() => { setTRef.current = setT; }, [setT]);

  const from = (clientX) => {
    const r = trackRef.current.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width));
  };

  const start = (clientX) => {
    const val = from(clientX);
    setDrag(true);
    setScrubT(val);
    scrubRef.current = val;
  };

  const move = (clientX) => {
    const val = from(clientX);
    setScrubT(val);
    scrubRef.current = val;
  };

  const end = () => {
    if (scrubRef.current !== null) setTRef.current(scrubRef.current);
    setScrubT(null);
    scrubRef.current = null;
    setDrag(false);
  };

  React.useEffect(() => {
    if (!drag) return;
    const onMove = (e) => move(e.clientX);
    const onUp = () => end();
    const onTouchMove = (e) => move(e.touches[0].clientX);
    const onTouchEnd = () => end();
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchmove", onTouchMove);
    window.addEventListener("touchend", onTouchEnd);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [drag]);

  const displayT = scrubT !== null ? scrubT : t;

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "auto 1fr auto",
      gap: 18, alignItems: "center",
      padding: "10px 18px",
      background: "linear-gradient(180deg, rgba(11,11,17,0.85), rgba(11,11,17,0.98))",
      borderTop: "1px solid rgba(255,255,255,0.06)",
      fontFamily: "JetBrains Mono, monospace",
    }}>
      {/* Transport */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <TransportBtn onClick={() => setT(Math.max(0, t - 0.02))} title="Rewind">
          <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 2v8M11 2L4 6l7 4V2z" fill="#E6E6EF"/></svg>
        </TransportBtn>
        <TransportBtn primary onClick={() => setPlaying(!playing)} title="Play/Pause">
          {playing
            ? <svg width="12" height="12" viewBox="0 0 12 12"><rect x="3" y="2" width="2.2" height="8" fill="#FFFFFF"/><rect x="6.8" y="2" width="2.2" height="8" fill="#FFFFFF"/></svg>
            : <svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 2l7 4-7 4V2z" fill="#FFFFFF"/></svg>
          }
        </TransportBtn>
        <TransportBtn onClick={() => setT(Math.min(1, t + 0.02))} title="Forward">
          <svg width="12" height="12" viewBox="0 0 12 12"><path d="M10 2v8M1 2l7 4-7 4V2z" fill="#E6E6EF"/></svg>
        </TransportBtn>
        <div style={{ width: 1, height: 20, background: "rgba(255,255,255,0.08)", margin: "0 6px" }}/>
        {[0.5, 1, 2, 4].map((s) => (
          <button key={s} onClick={() => setSpeed(s)} style={{
            padding: "4px 8px",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
            background: speed === s ? "#FF1E00" : "transparent",
            color: speed === s ? "#FFFFFF" : "rgba(180,180,200,0.6)",
            border: `1px solid ${speed === s ? "#FF1E00" : "rgba(255,255,255,0.08)"}`,
            cursor: "pointer",
          }}>{s}x</button>
        ))}
      </div>

      {/* Scrub */}
      <div
        ref={trackRef}
        onMouseDown={(e) => start(e.clientX)}
        onTouchStart={(e) => start(e.touches[0].clientX)}
        style={{
          position: "relative",
          height: 42,
          cursor: "pointer",
          display: "flex", alignItems: "center",
        }}>
        {/* Lap ticks */}
        <div style={{ position: "absolute", inset: "0 0 auto 0", top: 6, height: 2, background: "rgba(255,255,255,0.04)" }}/>
        <div style={{ position: "absolute", inset: "auto 0 6px 0", height: 14, background: "rgba(255,255,255,0.03)", borderTop: "1px solid rgba(255,255,255,0.04)", borderBottom: "1px solid rgba(255,255,255,0.04)" }}/>
        {(() => { const safeTotalLaps = Math.max(totalLaps, 1); return Array.from({ length: safeTotalLaps + 1 }).map((_, i) => {
          const pct = (i / safeTotalLaps) * 100;
          const major = i % 10 === 0;
          return (
            <div key={i} style={{
              position: "absolute", left: `${pct}%`, bottom: 6,
              width: 1, height: major ? 14 : 7,
              background: major ? "rgba(230,230,239,0.35)" : "rgba(230,230,239,0.12)",
            }}/>
          );
        }); })()}
        {(() => { const safeTotalLaps = Math.max(totalLaps, 1); return Array.from({ length: Math.floor(safeTotalLaps / 10) + 1 }).map((_, i) => (
          <div key={i} style={{
            position: "absolute", left: `${(i * 10 / safeTotalLaps) * 100}%`,
            top: 0, fontSize: 8, color: "rgba(180,180,200,0.5)",
            transform: "translateX(-50%)",
            letterSpacing: "0.1em",
          }}>L{i * 10 || 1}</div>
        )); })()}
        {/* SC zones */}
        {safetyCarEvents.map((e, i) => (
          <div key={i} style={{
            position: "absolute",
            left: `${e.start * 100}%`,
            width: `${(e.end - e.start) * 100}%`,
            top: 18, bottom: 8,
            background: "rgba(255,184,0,0.22)",
            borderLeft: "2px solid #FFB800",
            borderRight: "2px solid #FFB800",
          }}>
            <div style={{
              position: "absolute", top: -11, left: 0,
              background: "#FFB800", color: "#0B0B11",
              fontSize: 7, fontWeight: 800, letterSpacing: "0.12em",
              padding: "1px 4px",
            }}>SC</div>
          </div>
        ))}
        {/* Progress fill */}
        <div style={{
          position: "absolute", left: 0, top: 6,
          width: `${displayT * 100}%`, height: 2,
          background: "#FF1E00",
          boxShadow: "0 0 6px #FF1E00",
        }}/>
        {/* Playhead */}
        <div style={{
          position: "absolute", left: `${displayT * 100}%`, top: 0, bottom: 0,
          width: 2, background: "#FF1E00",
          boxShadow: "0 0 8px #FF1E00",
          transform: "translateX(-1px)",
        }}>
          <div style={{
            position: "absolute", top: -4, left: -5,
            width: 12, height: 6,
            background: "#FF1E00",
            clipPath: "polygon(0 0, 100% 0, 50% 100%)",
          }}/>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 10 }}>
        <div style={{ color: "rgba(180,180,200,0.6)", letterSpacing: "0.12em" }}>LAP</div>
        <div style={{ color: "#F6F6FA", fontWeight: 700, fontVariantNumeric: "tabular-nums", fontSize: 14 }}>
          {String(lap).padStart(2, "0")}/{totalLaps}
        </div>
      </div>
    </div>
  );
}

function TransportBtn({ children, onClick, title, primary }) {
  const [h, setH] = React.useState(false);
  return (
    <button
      onClick={onClick} title={title}
      onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{
        width: primary ? 32 : 26, height: 26,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: primary ? (h ? "#FF3A1E" : "#FF1E00") : (h ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.02)"),
        border: primary ? "1px solid #FF1E00" : "1px solid rgba(255,255,255,0.08)",
        color: "#FFFFFF", cursor: "pointer", padding: 0,
      }}>
      {children}
    </button>
  );
}

// Camera controls
function CameraControls({ rotateX, setRotateX, rotateZ, setRotateZ, zoom, setZoom, showDRS, setShowDRS, showLabels, setShowLabels, showProgress, setShowProgress }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 6,
      background: "linear-gradient(180deg, rgba(20,20,30,0.88), rgba(11,11,17,0.92))",
      border: "1px solid rgba(255,255,255,0.06)",
      padding: 10,
      fontFamily: "JetBrains Mono, monospace",
      fontSize: 9,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <div style={{ color: "rgba(180,180,200,0.5)", letterSpacing: "0.14em" }}>CAMERA</div>
        <button onClick={() => { setRotateX(62); setRotateZ(-18); setZoom(1); }} style={{
          padding: "2px 6px", background: "transparent",
          border: "1px solid rgba(255,255,255,0.08)",
          color: "rgba(180,180,200,0.7)", cursor: "pointer",
          fontFamily: "inherit", fontSize: 8, letterSpacing: "0.12em",
        }}>RESET</button>
      </div>
      <Slider label="TILT" value={rotateX} onChange={setRotateX} min={0} max={85} suffix="°"/>
      <Slider label="ROT"  value={rotateZ} onChange={setRotateZ} min={-180} max={180} suffix="°"/>
      <Slider label="ZOOM" value={zoom*100} onChange={(v) => setZoom(v/100)} min={50} max={400} suffix="%"/>
      <div style={{ height: 1, background: "rgba(255,255,255,0.05)", margin: "4px 0" }}/>
      <Toggle label="DRS ZONES"    on={showDRS}      onChange={setShowDRS} hotkey="D"/>
      <Toggle label="LABELS"       on={showLabels}   onChange={setShowLabels} hotkey="L"/>
      <Toggle label="PROGRESS BAR" on={showProgress} onChange={setShowProgress} hotkey="B"/>
    </div>
  );
}

function Slider({ label, value, onChange, min, max, suffix = "" }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "50px 1fr 38px", gap: 6, alignItems: "center" }}>
      <div style={{ color: "rgba(180,180,200,0.55)", letterSpacing: "0.1em" }}>{label}</div>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "#FF1E00", height: 2 }}/>
      <div style={{ color: "#E6E6EF", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>{Math.round(value)}{suffix}</div>
    </div>
  );
}

function Toggle({ label, on, onChange, hotkey }) {
  return (
    <button onClick={() => onChange(!on)} style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "4px 2px",
      background: "transparent", border: "none",
      color: on ? "#E6E6EF" : "rgba(180,180,200,0.55)",
      fontFamily: "inherit", fontSize: 9,
      letterSpacing: "0.1em",
      cursor: "pointer", width: "100%",
    }}>
      <span>{label} {hotkey && <span style={{ opacity: 0.5 }}>[{hotkey}]</span>}</span>
      <span style={{
        width: 22, height: 10, background: on ? "#FF1E00" : "rgba(255,255,255,0.08)",
        position: "relative",
        boxShadow: on ? "0 0 6px rgba(255,30,0,0.6)" : "none",
      }}>
        <span style={{
          position: "absolute", top: 1, left: on ? 13 : 1,
          width: 8, height: 8, background: "#FFFFFF",
          transition: "left 120ms",
        }}/>
      </span>
    </button>
  );
}

window.TopBar = TopBar;
window.Timeline = Timeline;
window.CameraControls = CameraControls;
