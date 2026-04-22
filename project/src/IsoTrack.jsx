// Isometric 3D track view. SVG rendered in a 3D-transformed container.
// Supports: rotate, zoom, DRS zones toggle, driver labels toggle,
// safety car deployment animation, clickable cars.

const { TEAMS, DRIVERS, COMPOUNDS } = window.APEX;

// Bounding box of the circuit → viewport
function bounds(pts) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of pts) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, maxX, minY, maxY };
}

function computeDerived(circuit) {
  const B = bounds(circuit);
  const CIRCUIT_EXTENT = Math.max(B.maxX - B.minX, B.maxY - B.minY);
  const S = Math.max(1, CIRCUIT_EXTENT / 600);
  const PAD = 80 * S;
  const VB_W = (B.maxX - B.minX) + PAD * 2;
  const VB_H = (B.maxY - B.minY) + PAD * 2;
  const OX = -B.minX + PAD;
  const OY = -B.minY + PAD;
  const CENTROID = {
    x: circuit.reduce((s, p) => s + p.x, 0) / circuit.length,
    y: circuit.reduce((s, p) => s + p.y, 0) / circuit.length,
  };
  return { B, CIRCUIT_EXTENT, S, PAD, VB_W, VB_H, OX, OY, CENTROID };
}

function pathFromPts(pts, OX, OY, closed = true) {
  let d = `M ${pts[0].x + OX} ${pts[0].y + OY}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x + OX} ${pts[i].y + OY}`;
  if (closed) d += " Z";
  return d;
}

function outwardNormal(idx, circuit, centroid) {
  const n = circuit.length;
  const p = circuit[idx];
  const p2 = circuit[(idx + 1) % n];
  const dx = p2.x - p.x, dy = p2.y - p.y;
  const mag = Math.hypot(dx, dy) || 1;
  const nx = -dy / mag, ny = dx / mag;
  const dPlus = Math.hypot(p.x + nx - centroid.x, p.y + ny - centroid.y);
  const dMinus = Math.hypot(p.x - nx - centroid.x, p.y - ny - centroid.y);
  return dPlus >= dMinus ? { nx, ny } : { nx: -nx, ny: -ny };
}

function textColorFor(hex) {
  if (!hex || hex.length < 7) return "#FFFFFF";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const Y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return Y > 140 ? "#0B0B11" : "#FFFFFF";
}

function sliceRange(start, end, circuit) {
  const out = [];
  const n = circuit.length;
  if (start < end) {
    for (let i = start; i <= end; i++) out.push(circuit[i]);
  } else {
    for (let i = start; i < n; i++) out.push(circuit[i]);
    for (let i = 0; i <= end; i++) out.push(circuit[i]);
  }
  return out;
}

function IsoTrack({
  standings,
  safetyCar,
  pinned,
  secondary,
  onPickDriver,
  showDRS = true,
  showLabels = true,
  rotateX = 62,
  rotateZ = -18,
  zoom = 1,
}) {
  const [hover, setHover] = React.useState(null);

  // Memoize geometry derivations against CIRCUIT.length so they recompute when snapshot arrives
  const CIRCUIT = window.APEX.CIRCUIT;
  const SECTORS = window.APEX.SECTORS;
  const DRS_ZONES = window.APEX.DRS_ZONES;
  const geoKey = CIRCUIT.length;
  const { B, CIRCUIT_EXTENT, S, PAD, VB_W, VB_H, OX, OY, CENTROID } = React.useMemo(
    () => computeDerived(CIRCUIT),
    [geoKey]
  );

  const trackPath = pathFromPts(CIRCUIT, OX, OY, true);

  // Offset path for track shoulders (cheap outline)
  const shoulderScale = 1.012;
  const shoulderPts = CIRCUIT.map((p) => ({ x: p.x * shoulderScale, y: p.y * shoulderScale }));
  const shoulderPath = pathFromPts(shoulderPts, OX, OY, true);

  // Sector start/finish marker pts
  const sfIdx = 0;
  const sf = CIRCUIT[sfIdx];

  return (
    <div style={{
      position: "absolute", inset: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      perspective: 1800,
      overflow: "hidden",
    }}>
      {/* Ambient floor grid */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `
          radial-gradient(ellipse at center, rgba(255,30,0,0.08) 0%, transparent 55%),
          linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)
        `,
        backgroundSize: "100% 100%, 40px 40px, 40px 40px",
        transform: `rotateX(${rotateX}deg) rotateZ(${rotateZ}deg) scale(${zoom * 2.6})`,
        transformOrigin: "center center",
        transformStyle: "preserve-3d",
        pointerEvents: "none",
      }} />

      {/* Track itself — 3D rotated */}
      <div style={{
        position: "relative",
        width: "82%", height: "82%",
        transform: `rotateX(${rotateX}deg) rotateZ(${rotateZ}deg) scale(${zoom * 2.0})`,
        transformStyle: "preserve-3d",
        transition: "transform 240ms cubic-bezier(.2,.7,.2,1)",
      }}>
        {/* Track shadow (flat plate) */}
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} style={{
          position: "absolute", inset: 0,
          width: "100%", height: "100%",
          transform: "translateZ(-8px)",
          filter: "blur(16px)",
          opacity: 0.7,
        }}>
          <path d={trackPath} fill="#000" />
        </svg>

        {/* Base plate (deeper than track) */}
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} style={{
          position: "absolute", inset: 0,
          width: "100%", height: "100%",
        }}>
          <defs>
            <linearGradient id="plateGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#1C1C28" />
              <stop offset="100%" stopColor="#0B0B11" />
            </linearGradient>
            <radialGradient id="trackGlow" cx="0.5" cy="0.5" r="0.6">
              <stop offset="0%" stopColor="#FF1E00" stopOpacity="0.25"/>
              <stop offset="100%" stopColor="#FF1E00" stopOpacity="0"/>
            </radialGradient>
          </defs>

          {/* Glow under track */}
          <path d={trackPath} fill="url(#trackGlow)" style={{ filter: "blur(18px)" }}/>

          {/* Outer shoulder (runoff) */}
          <path d={shoulderPath} fill="none" stroke="#23232F" strokeWidth={34*S} strokeLinejoin="round" />
          {/* Main track */}
          <path d={trackPath} fill="none" stroke="#0E0E16" strokeWidth={26*S} strokeLinejoin="round" />
          {/* Track surface */}
          <path d={trackPath} fill="none" stroke="#2A2A38" strokeWidth={22*S} strokeLinejoin="round" />
          {/* Racing line (subtle) */}
          <path d={trackPath} fill="none" stroke="#3A3A4A" strokeWidth={1.6*S} strokeDasharray={`${6*S} ${10*S}`} opacity="0.6"/>

          {/* DRS zones (emissive red tint over the track) */}
          {showDRS && DRS_ZONES.map((z, i) => {
            const seg = sliceRange(z.start, z.end, CIRCUIT);
            const d = pathFromPts(seg, OX, OY, false);
            return (
              <g key={i}>
                <path d={d} fill="none" stroke="#FF1E00" strokeWidth={22*S} strokeLinejoin="round" opacity="0.22"/>
                <path d={d} fill="none" stroke="#FF1E00" strokeWidth={3*S}  strokeLinejoin="round" opacity="0.9" strokeDasharray={`${4*S} ${6*S}`}/>
              </g>
            );
          })}

          {/* Sector markers */}
          {SECTORS.map((s, i) => {
            const p = CIRCUIT[s.idx];
            const p2 = CIRCUIT[(s.idx + 1) % CIRCUIT.length];
            const dx = p2.x - p.x, dy = p2.y - p.y;
            const mag = Math.hypot(dx, dy) || 1;
            const nx = -dy / mag, ny = dx / mag;
            const len = 18 * S;
            const x1 = p.x + OX + nx * len, y1 = p.y + OY + ny * len;
            const x2 = p.x + OX - nx * len, y2 = p.y + OY - ny * len;
            return (
              <g key={i}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={s.color} strokeWidth={3*S} opacity="0.85"/>
                <circle cx={p.x + OX} cy={p.y + OY} r={3.5*S} fill={s.color}/>
              </g>
            );
          })}

          {/* Start/finish checker */}
          <StartFinish pt={sf} next={CIRCUIT[1]} S={S} OX={OX} OY={OY} />

          {/* Pit lane (offset parallel on part of the track) */}
          <PitLane circuit={CIRCUIT} S={S} OX={OX} OY={OY} />

          {/* Cars — Phase 5 visibility overhaul */}
          {(() => {
            const BUCKET = 6;
            const buckets = {};
            const activeCars = standings.filter(s => s.status !== "OUT");
            for (const s of activeCars) {
              const key = Math.floor(s.trackIdx / BUCKET);
              if (!buckets[key]) buckets[key] = [];
              buckets[key].push(s);
            }
            const spreadOffsets = {};
            for (const [, group] of Object.entries(buckets)) {
              group.sort((a, b) => a.pos - b.pos);
              const n = group.length;
              if (n <= 1) continue;
              for (let i = 0; i < n; i++) {
                const { nx, ny } = outwardNormal(group[i].trackIdx, CIRCUIT, CENTROID);
                const off = (i - (n - 1) / 2) * 14 * S;
                spreadOffsets[group[i].driver.code] = { dx: nx * off, dy: ny * off };
              }
            }
            const outCars = standings.filter(s => s.status === "OUT");
            return [
              ...outCars.map((s) => {
                const p = CIRCUIT[s.trackIdx];
                return (
                  <g key={s.driver.code} transform={`translate(${p.x + OX}, ${p.y + OY}) scale(${S})`} opacity="0.3">
                    <circle r="11" fill="none" stroke="#555" strokeWidth="1.5"/>
                    <text x="0" y="3.5" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9" fontWeight="700" fill="#555">{s.pos}</text>
                  </g>
                );
              }),
              ...activeCars.map((s) => {
                const p = CIRCUIT[s.trackIdx];
                const team = TEAMS[s.driver.team];
                const isPinned = pinned === s.driver.code;
                const isSecondary = secondary === s.driver.code;
                const isHover = hover === s.driver.code;
                const off = spreadOffsets[s.driver.code] || { dx: 0, dy: 0 };
                const { nx: onx, ny: ony } = outwardNormal(s.trackIdx, CIRCUIT, CENTROID);
                const isPit = s.status === "PIT" || s.pit;
                const cx = p.x + OX + off.dx;
                const cy = p.y + OY + off.dy;
                const txtFill = textColorFor(team.color);
                const speedFrac = Math.min(1, (s.speedKph || 0) / 350);
                const haloOpacity = isPit ? 0 : 0.2 + 0.5 * speedFrac;
                return (
                  <g
                    key={s.driver.code}
                    transform={`translate(${cx}, ${cy}) scale(${S})`}
                    style={{ cursor: "pointer", opacity: isPit ? 0.5 : 1 }}
                    onMouseEnter={() => setHover(s.driver.code)}
                    onMouseLeave={() => setHover(null)}
                    onClick={(e) => onPickDriver && onPickDriver(s.driver.code, e)}
                  >
                    {isPinned && (
                      <circle r="16" fill="none" stroke="#FF1E00" strokeWidth="2" strokeDasharray="4 3"/>
                    )}
                    {isSecondary && (
                      <circle r="16" fill="none" stroke="#00D9FF" strokeWidth="2" strokeDasharray="4 3"/>
                    )}
                    {isHover && (
                      <circle r="22" fill={isSecondary ? "#00D9FF" : team.color} opacity="0.22"/>
                    )}
                    {!isPit && (
                      <circle r="15" fill="none" stroke={team.color} strokeWidth="1" opacity={haloOpacity}/>
                    )}
                    <circle r="11" fill={team.color} stroke="#0B0B11" strokeWidth="1.5"/>
                    <circle r="11" fill="none" stroke="rgba(255,255,255,0.25)" strokeWidth="0.5"/>
                    <text
                      x="0" y="3.5"
                      textAnchor="middle"
                      fontFamily="JetBrains Mono, monospace"
                      fontSize="9"
                      fontWeight="700"
                      fill={txtFill}
                    >
                      {s.pos}
                    </text>
                    {isPit && (
                      <text x="0" y="-8" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="7" fontWeight="700" fill="#FFB800">P</text>
                    )}
                    {showLabels && (
                      <g transform={`translate(${onx * 18}, ${ony * 18})`}>
                        <rect x="0" y="-7" width="34" height="12" rx="2" fill="rgba(11,11,17,0.85)" stroke={team.color} strokeWidth="0.6"/>
                        <text
                          x="17" y="2"
                          textAnchor="middle"
                          fontFamily="JetBrains Mono, monospace"
                          fontSize="8"
                          fontWeight="700"
                          fill="#F4F4F8"
                          letterSpacing="0.08em"
                        >
                          {s.driver.code}
                        </text>
                      </g>
                    )}
                    {s.inDRS && showDRS && (
                      <g transform={`translate(${-onx * 24}, ${-ony * 24})`}>
                        <rect x="0" y="-6" width="22" height="10" rx="1" fill="#FF1E00"/>
                        <text x="11" y="2" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="7" fontWeight="700" fill="#FFFFFF">DRS</text>
                      </g>
                    )}
                  </g>
                );
              }),
            ];
          })()}

          {/* Safety car */}
          {safetyCar && <SafetyCarGlyph sc={safetyCar} circuit={CIRCUIT} S={S} OX={OX} OY={OY} />}
        </svg>
      </div>

      {/* Corner labels (flat, on top of 3D plate, don't tilt) */}
      <CornerLabels rotateX={rotateX} rotateZ={rotateZ} zoom={zoom} circuit={CIRCUIT} S={S} OX={OX} OY={OY} VB_W={VB_W} VB_H={VB_H} />
    </div>
  );
}

function StartFinish({ pt, next, S, OX, OY }) {
  const dx = next.x - pt.x, dy = next.y - pt.y;
  const mag = Math.hypot(dx, dy) || 1;
  const nx = -dy / mag, ny = dx / mag;
  const cx = pt.x + OX, cy = pt.y + OY;
  const cells = 6;
  const w = 22 * S;
  const rects = [];
  for (let i = 0; i < cells; i++) {
    const off = (i - cells / 2) * (w / cells);
    const x = cx + nx * off;
    const y = cy + ny * off;
    rects.push(
      <rect key={i} x={x - 2*S} y={y - 6*S} width={4*S} height={12*S}
        fill={i % 2 === 0 ? "#FFFFFF" : "#0B0B11"}
        transform={`rotate(${Math.atan2(ny, nx) * 180 / Math.PI}, ${x}, ${y})`}
      />
    );
  }
  return (
    <g>
      {rects}
      <text x={cx + nx * 26 * S} y={cy + ny * 26 * S}
        fontFamily="JetBrains Mono, monospace"
        fontSize={8*S}
        fontWeight="700"
        fill="#FF1E00"
        textAnchor="middle"
      >S/F</text>
    </g>
  );
}

function PitLane({ circuit, S, OX, OY }) {
  // Offset pit lane parallel to ~55% of circuit onward, slightly inside
  const startIdx = Math.floor(circuit.length * 0.55);
  const seg = [];
  for (let i = startIdx; i < circuit.length; i++) seg.push(circuit[i]);
  for (let i = 0; i < 15; i++) seg.push(circuit[i]);
  const offset = seg.map((p, i) => {
    const n = seg[Math.min(i + 1, seg.length - 1)];
    const dx = n.x - p.x, dy = n.y - p.y;
    const m = Math.hypot(dx, dy) || 1;
    // perpendicular inward
    return { x: p.x + (-dy / m) * -20 * S, y: p.y + (dx / m) * -20 * S };
  });
  let d = `M ${offset[0].x + OX} ${offset[0].y + OY}`;
  for (let i = 1; i < offset.length; i++) d += ` L ${offset[i].x + OX} ${offset[i].y + OY}`;
  return (
    <g>
      <path d={d} fill="none" stroke="#15151E" strokeWidth={10*S} strokeLinecap="round"/>
      <path d={d} fill="none" stroke="#2A2A38" strokeWidth={7*S} strokeLinecap="round"/>
      <path d={d} fill="none" stroke="#FFFFFF" strokeWidth={0.8*S} strokeDasharray={`${2*S} ${4*S}`} opacity="0.5"/>
    </g>
  );
}

function SafetyCarGlyph({ sc, circuit, S, OX, OY }) {
  const p = circuit[sc.trackIdx];
  const pulseR = 22 + Math.sin(sc.pulse) * 6;
  return (
    <g transform={`translate(${p.x + OX}, ${p.y + OY}) scale(${S})`} opacity={sc.alpha}>
      <circle r={pulseR} fill="#FFB800" opacity="0.25"/>
      <circle r="13" fill="#FFB800" stroke="#0B0B11" strokeWidth="2"/>
      <text x="0" y="3" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fontWeight="700" fill="#0B0B11">SC</text>
      <g transform="translate(16, -14)">
        <rect x="0" y="-7" width="60" height="14" rx="2" fill="#FFB800"/>
        <text x="30" y="3" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fontWeight="700" fill="#0B0B11" letterSpacing="0.1em">
          {sc.phase === "deploying" ? "SC DEPLOYING" : sc.phase === "returning" ? "SC IN" : "SAFETY CAR"}
        </text>
      </g>
    </g>
  );
}

function CornerLabels({ rotateX, rotateZ, zoom, circuit, S, OX, OY, VB_W, VB_H }) {
  // Place corner numbers at tight-radius points along circuit
  const corners = [];
  const n = circuit.length;
  for (let i = 0; i < n; i++) {
    const pPrev = circuit[(i - 5 + n) % n];
    const p     = circuit[i];
    const pNext = circuit[(i + 5) % n];
    const v1x = p.x - pPrev.x, v1y = p.y - pPrev.y;
    const v2x = pNext.x - p.x, v2y = pNext.y - p.y;
    const a1 = Math.atan2(v1y, v1x);
    const a2 = Math.atan2(v2y, v2x);
    let da = Math.abs(a2 - a1);
    if (da > Math.PI) da = 2 * Math.PI - da;
    corners.push({ idx: i, curvature: da });
  }
  // Non-max suppression: take peaks > threshold, min spacing
  const picked = [];
  const sorted = [...corners].sort((a, b) => b.curvature - a.curvature);
  for (const c of sorted) {
    if (c.curvature < 0.35) break;
    if (picked.every((q) => Math.min(Math.abs(q.idx - c.idx), n - Math.abs(q.idx - c.idx)) > 14)) {
      picked.push(c);
    }
    if (picked.length >= 14) break;
  }
  picked.sort((a, b) => a.idx - b.idx);

  return (
    <div style={{
      position: "absolute", inset: 0,
      pointerEvents: "none",
      transform: `rotateX(${rotateX}deg) rotateZ(${rotateZ}deg) scale(${zoom * 2.0})`,
      transformStyle: "preserve-3d",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} style={{ width: "82%", height: "82%" }}>
        {picked.map((c, n) => {
          const p = circuit[c.idx];
          const pn = circuit[(c.idx + 1) % circuit.length];
          const dx = pn.x - p.x, dy = pn.y - p.y;
          const mag = Math.hypot(dx, dy) || 1;
          const nx = -dy / mag, ny = dx / mag;
          const cx = p.x + OX + nx * 28 * S;
          const cy = p.y + OY + ny * 28 * S;
          return (
            <g key={c.idx} transform={`translate(${cx}, ${cy})`}>
              <circle r={7*S} fill="#0B0B11" stroke="#FF1E00" strokeWidth={0.8*S} opacity="0.9"/>
              <text y={2.5*S} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={6.5*S} fontWeight="700" fill="#FF1E00">T{n + 1}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

window.IsoTrack = IsoTrack;
