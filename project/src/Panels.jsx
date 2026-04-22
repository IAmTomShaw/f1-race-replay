// Right-side panels: tyre strategy, pit predictor, ghost radar, etc.

const { TEAMS, COMPOUNDS, DRIVERS, getStints, getPitStops } = window.APEX;

// Map fastf1 compound strings → APEX keys
const COMPOUND_KEY = {
  SOFT: "S", MEDIUM: "M", HARD: "H",
  INTERMEDIATE: "I", WET: "W", UNKNOWN: "M",
};

// Stint strategy strip for top-10 drivers — uses real stint & pit stop data
function StrategyStrip({ standings, totalLaps, lap }) {
  const top = standings.slice(0, 10);
  return (
    <div style={{
      background: "linear-gradient(180deg, rgba(20,20,30,0.92), rgba(11,11,17,0.94))",
      border: "1px solid rgba(255,255,255,0.06)",
      overflow: "hidden",
    }}>
      <PanelHeader title="TYRE STRATEGY" meta={`LAP ${lap}/${totalLaps}`}/>
      <div style={{ padding: "6px 10px", fontFamily: "JetBrains Mono, monospace" }}>
        {top.map((s) => {
          const team = TEAMS[s.driver.team];
          const rawStints = getStints(s.driver.code);
          const pitStops = getPitStops(s.driver.code);
          // Convert real stints → { start, end, c } for rendering
          const stops = rawStints.length > 0
            ? rawStints.map((st) => ({
                start: st.start_lap - 1,   // 0-indexed for bar positioning
                end: st.end_lap,
                c: COMPOUND_KEY[st.compound] || "M",
              }))
            : [{ start: 0, end: totalLaps, c: "M" }]; // fallback
          return (
            <div key={s.driver.code} style={{
              display: "grid", gridTemplateColumns: "28px 36px 1fr",
              gap: 8, alignItems: "center",
              padding: "3px 0",
              fontSize: 9,
            }}>
              <div style={{ color: "rgba(180,180,200,0.5)", fontVariantNumeric: "tabular-nums" }}>
                P{String(s.pos).padStart(2, "0")}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div style={{ width: 2, height: 10, background: team.color }}/>
                <div style={{ color: "#E6E6EF", fontWeight: 700, letterSpacing: "0.06em" }}>{s.driver.code}</div>
              </div>
              <div style={{ position: "relative", height: 10, background: "rgba(255,255,255,0.04)" }}>
                {stops.map((stint, i) => {
                  const sx = (stint.start / totalLaps) * 100;
                  const sw = ((stint.end - stint.start) / totalLaps) * 100;
                  return (
                    <div key={i} style={{
                      position: "absolute", left: `${sx}%`, width: `${sw}%`, top: 0, bottom: 0,
                      background: COMPOUNDS[stint.c].color,
                      opacity: stint.end < lap ? 0.55 : stint.start > lap ? 0.25 : 0.85,
                      borderRight: "1px solid rgba(11,11,17,0.7)",
                    }}/>
                  );
                })}
                {/* Pit stop markers */}
                {pitStops.map((ps, i) => (
                  <div key={`pit-${i}`} style={{
                    position: "absolute",
                    left: `${(ps.lap / totalLaps) * 100}%`,
                    top: -3, bottom: -3, width: 2,
                    background: "#FFB800",
                    borderRadius: 1,
                    zIndex: 2,
                  }}/>
                ))}
                {/* Current lap marker */}
                <div style={{
                  position: "absolute", left: `${(lap / totalLaps) * 100}%`,
                  top: -2, bottom: -2, width: 1, background: "#FFFFFF",
                  zIndex: 3,
                }}/>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Compact gap-to-leader visualizer (spider)
function GapViz({ standings, pinned }) {
  const top = standings.slice(0, 10);
  const maxGap = Math.max(...top.map(s => s.gap ?? 0), 1);
  return (
    <div style={{
      background: "linear-gradient(180deg, rgba(20,20,30,0.92), rgba(11,11,17,0.94))",
      border: "1px solid rgba(255,255,255,0.06)",
    }}>
      <PanelHeader title="GAP TO LEADER"/>
      <div style={{ padding: "6px 10px", fontFamily: "JetBrains Mono, monospace" }}>
        {top.map((s) => {
          const team = TEAMS[s.driver.team];
          const pct = (s.gap / maxGap) * 100;
          const isPinned = pinned === s.driver.code;
          return (
            <div key={s.driver.code} style={{
              display: "grid", gridTemplateColumns: "40px 1fr 58px",
              gap: 6, alignItems: "center", fontSize: 9,
              padding: "2.5px 0",
            }}>
              <div style={{ color: isPinned ? "#FF1E00" : "#E6E6EF", fontWeight: 700 }}>
                {s.driver.code}
              </div>
              <div style={{ position: "relative", height: 3, background: "rgba(255,255,255,0.04)" }}>
                <div style={{ position: "absolute", left: 0, width: `${pct}%`, height: "100%", background: team.color }}/>
              </div>
              <div style={{ color: "rgba(230,230,239,0.8)", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>
                {s.gap === 0 ? "LEADER" : `+${s.gap.toFixed(2)}`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Event feed / race control messages
function RaceFeed({ events }) {
  return (
    <div style={{
      background: "linear-gradient(180deg, rgba(20,20,30,0.92), rgba(11,11,17,0.94))",
      border: "1px solid rgba(255,255,255,0.06)",
      display: "flex", flexDirection: "column",
      minHeight: 0, flex: 1,
    }}>
      <PanelHeader title="RACE CONTROL" meta={`${events.length} MSGS`}/>
      <div style={{ overflow: "auto", flex: 1, fontFamily: "JetBrains Mono, monospace", fontSize: 10 }}>
        {events.map((e, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "54px 42px 1fr",
            gap: 8, padding: "6px 10px",
            borderBottom: "1px solid rgba(255,255,255,0.03)",
            alignItems: "start",
          }}>
            <div style={{ color: "rgba(180,180,200,0.5)", fontSize: 9, fontVariantNumeric: "tabular-nums" }}>
              {e.time}
            </div>
            <div style={{
              fontSize: 8, letterSpacing: "0.12em", fontWeight: 700,
              padding: "1px 4px",
              color: e.tag === "SC" ? "#0B0B11" : e.tag === "FLAG" ? "#0B0B11" : "#E6E6EF",
              background: e.tag === "SC" ? "#FFB800" : e.tag === "FLAG" ? "#FFD93A" : e.tag === "INFO" ? "rgba(255,255,255,0.06)" : "rgba(255,30,0,0.3)",
              textAlign: "center",
              alignSelf: "start",
            }}>
              {e.tag}
            </div>
            <div style={{ color: "#E6E6EF", fontSize: 10, lineHeight: 1.35, letterSpacing: "0.03em" }}>
              {e.msg}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

window.StrategyStrip = StrategyStrip;
window.GapViz = GapViz;
window.RaceFeed = RaceFeed;
