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
  const n = pts.length;
  if (n < 2) return "";
  if (n === 2) return `M ${pts[0].x+OX} ${pts[0].y+OY} L ${pts[1].x+OX} ${pts[1].y+OY}`;

  const alpha = 0.5; // centripetal — avoids self-intersection on tight hairpins

  function getPoint(i) {
    if (closed) return pts[((i % n) + n) % n];
    if (i < 0)  return { x: 2*pts[0].x - pts[1].x, y: 2*pts[0].y - pts[1].y };
    if (i >= n)  return { x: 2*pts[n-1].x - pts[n-2].x, y: 2*pts[n-1].y - pts[n-2].y };
    return pts[i];
  }

  function knotDist(a, b) {
    return Math.pow(Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1e-12), alpha);
  }

  let d = `M ${pts[0].x+OX} ${pts[0].y+OY}`;
  const segCount = closed ? n : n - 1;

  for (let i = 0; i < segCount; i++) {
    const p0 = getPoint(i - 1);
    const p1 = getPoint(i);
    const p2 = getPoint(i + 1);
    const p3 = getPoint(i + 2);

    const d1 = knotDist(p0, p1);
    const d2 = knotDist(p1, p2);
    const d3 = knotDist(p2, p3);

    const b1x = p1.x + (p2.x - p0.x) * d2 / (3 * (d1 + d2));
    const b1y = p1.y + (p2.y - p0.y) * d2 / (3 * (d1 + d2));
    const b2x = p2.x - (p3.x - p1.x) * d2 / (3 * (d2 + d3));
    const b2y = p2.y - (p3.y - p1.y) * d2 / (3 * (d2 + d3));

    d += ` C ${b1x+OX} ${b1y+OY} ${b2x+OX} ${b2y+OY} ${p2.x+OX} ${p2.y+OY}`;
  }

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
  viewMode = "iso",
}) {
  // Top-down mode flattens tilt only — rotateZ still spins the map. No fake shadow.
  const isTop = viewMode === "top";
  const rX = isTop ? 0 : rotateX;
  const rZ = rotateZ;
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

  // Guard against initial render before geometry fetch resolves (CIRCUIT may be a single-point placeholder).
  if (CIRCUIT.length < 2) {
    return <div style={{ position: "absolute", inset: 0 }} />;
  }

  // Zoom is split between SVG viewBox (for crisp vector re-rasterization) and
  // CSS scale (for framing/visible area). Product equals the full zoom. We bias
  // toward CSS scale (pow 2/3) so framing matches original behavior and the
  // track does not clip at the viewport edges; viewBox takes pow 1/3 for some
  // vector sharpness benefit without over-narrowing the visible area.
  const z = Math.max(0.1, zoom);
  const zVB = Math.pow(z, 1 / 3);
  const zCSS = Math.pow(z, 2 / 3);
  const vbW = VB_W / zVB;
  const vbH = VB_H / zVB;
  const vbX = VB_W / 2 - vbW / 2;
  const vbY = VB_H / 2 - vbH / 2;
  const viewBox = `${vbX} ${vbY} ${vbW} ${vbH}`;

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
        transform: `rotateX(${rX}deg) rotateZ(${rZ}deg) scale(${zoom * 2.6})`,
        transformOrigin: "center center",
        transformStyle: "preserve-3d",
        pointerEvents: "none",
      }} />

      {/* Track itself — 3D rotated. Zoom is split between CSS scale (for framing/extent
          of view) and SVG viewBox narrowing (for sharp re-rasterization of vectors).
          The product is the same as the old pure-CSS zoom*2.0, but half the magnification
          comes from re-rasterized vectors rather than upsampled bitmap. */}
      <div style={{
        position: "relative",
        width: "82%", height: "82%",
        transform: `rotateX(${rX}deg) rotateZ(${rZ}deg) scale(${zCSS * 2.0})`,
        transformStyle: "preserve-3d",
        transition: "transform 240ms cubic-bezier(.2,.7,.2,1)",
      }}>
        {/* Track shadow (flat plate) — iso only; flat in top-down. */}
        {!isTop && <svg viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          shapeRendering="geometricPrecision" textRendering="geometricPrecision"
          style={{
          position: "absolute", inset: 0,
          width: "100%", height: "100%",
          transform: "translateZ(-8px)",
          filter: "blur(16px)",
          opacity: 0.7,
        }}>
          <path d={trackPath} fill="#000" />
        </svg>}

        {/* Base plate (deeper than track) */}
        <svg viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
          shapeRendering="geometricPrecision" textRendering="geometricPrecision"
          style={{
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
            <pattern id="checker" width="8" height="8" patternUnits="userSpaceOnUse">
              <rect width="4" height="4" fill="#FFFFFF"/>
              <rect x="4" width="4" height="4" fill="#0B0B11"/>
              <rect y="4" width="4" height="4" fill="#0B0B11"/>
              <rect x="4" y="4" width="4" height="4" fill="#FFFFFF"/>
            </pattern>
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
      <CornerLabels rotateX={rX} rotateZ={rZ} zoom={zoom} viewBox={viewBox} circuit={CIRCUIT} S={S} OX={OX} OY={OY} VB_W={VB_W} VB_H={VB_H} />
    </div>
  );
}

function StartFinish({ pt, next, S, OX, OY }) {
  const dx = next.x - pt.x, dy = next.y - pt.y;
  const mag = Math.hypot(dx, dy) || 1;
  const nx = -dy / mag, ny = dx / mag;
  const dirX = dx / mag, dirY = dy / mag;
  const cx = pt.x + OX, cy = pt.y + OY;
  const angle = Math.atan2(ny, nx) * 180 / Math.PI;

  // Direction arrow: tip 15*S ahead, base 9*S ahead, half-width 4*S
  const tipX = cx + dirX * 15 * S, tipY = cy + dirY * 15 * S;
  const baseL = `${cx + dirX*9*S + nx*4*S},${cy + dirY*9*S + ny*4*S}`;
  const baseR = `${cx + dirX*9*S - nx*4*S},${cy + dirY*9*S - ny*4*S}`;

  return (
    <g shapeRendering="geometricPrecision">
      {/* Checkered band across the track */}
      <rect
        x={cx - 16*S} y={cy - 4*S}
        width={32*S} height={8*S}
        fill="url(#checker)"
        transform={`rotate(${angle}, ${cx}, ${cy})`}
      />
      {/* Red GRID line with glow */}
      <line
        x1={cx + nx*16*S} y1={cy + ny*16*S}
        x2={cx - nx*16*S} y2={cy - ny*16*S}
        stroke="#FF1E00" strokeWidth={3*S}
        style={{ filter: "drop-shadow(0 0 4px #FF1E00)" }}
      />
      {/* Direction arrow */}
      <polygon
        points={`${tipX},${tipY} ${baseL} ${baseR}`}
        fill="#FF1E00"
      />
      {/* S/F label with background */}
      <g transform={`translate(${cx + nx*26*S}, ${cy + ny*26*S})`}>
        <rect x={-12*S} y={-7*S} width={24*S} height={14*S} rx={2*S}
          fill="rgba(11,11,17,0.85)" stroke="#FF1E00" strokeWidth={0.8*S}/>
        <text
          textAnchor="middle" y={3.5*S}
          fontFamily="JetBrains Mono, monospace"
          fontSize={Math.max(8, 8*S)}
          fontWeight="700"
          fill="#FF1E00"
        >S/F</text>
      </g>
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
  const d = pathFromPts(offset, OX, OY, false);
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

function CornerLabels({ rotateX, rotateZ, zoom, viewBox, circuit, S, OX, OY, VB_W, VB_H }) {
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

  // 2D projection: rotateZ then flatten y by cos(rotateX)
  const cosX = Math.cos(rotateX * Math.PI / 180);
  const cosZ = Math.cos(rotateZ * Math.PI / 180);
  const sinZ = Math.sin(rotateZ * Math.PI / 180);
  function project(x, y) {
    const vx = (x - VB_W / 2) * cosZ - (y - VB_H / 2) * sinZ;
    const vy = ((x - VB_W / 2) * sinZ + (y - VB_H / 2) * cosZ) * cosX;
    return { x: VB_W / 2 + vx, y: VB_H / 2 + vy };
  }

  return (
    <div style={{
      position: "absolute", inset: 0,
      pointerEvents: "none",
      transform: `scale(${Math.pow(Math.max(0.1, zoom), 2 / 3) * 2.0})`,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <svg viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        shapeRendering="geometricPrecision" textRendering="geometricPrecision"
        style={{ width: "82%", height: "82%" }}>
        <defs>
          <filter id="cornerShadow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="1.5"/>
            <feOffset dx="0" dy="1"/>
            <feComponentTransfer><feFuncA type="linear" slope="0.4"/></feComponentTransfer>
            <feMerge>
              <feMergeNode/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        {picked.map((c, i) => {
          const p = circuit[c.idx];
          const pn = circuit[(c.idx + 1) % circuit.length];
          const dx = pn.x - p.x, dy = pn.y - p.y;
          const mag = Math.hypot(dx, dy) || 1;
          const nx = -dy / mag, ny = dx / mag;
          // Apex and label positions in viewBox space
          const apexVX = p.x + OX, apexVY = p.y + OY;
          const labelVX = p.x + OX + nx * 28 * S, labelVY = p.y + OY + ny * 28 * S;
          // Project through the 3D transform
          const projApex = project(apexVX, apexVY);
          const projLabel = project(labelVX, labelVY);
          const R = Math.max(10, 7 * S);
          const FS = Math.max(10, 6.5 * S);
          // Connector line from circle edge toward apex
          const connDx = projApex.x - projLabel.x;
          const connDy = projApex.y - projLabel.y;
          const connMag = Math.hypot(connDx, connDy) || 1;
          const connStartX = projLabel.x + (connDx / connMag) * R;
          const connStartY = projLabel.y + (connDy / connMag) * R;
          return (
            <g key={c.idx}>
              {/* Connector line from circle edge to apex */}
              <line x1={connStartX} y1={connStartY} x2={projApex.x} y2={projApex.y}
                stroke="#FF1E00" strokeWidth={1} opacity="0.5" vectorEffect="non-scaling-stroke"/>
              <g filter="url(#cornerShadow)">
                {/* Outer white halo */}
                <circle cx={projLabel.x} cy={projLabel.y} r={R + 3}
                  fill="none" stroke="#FFFFFF" strokeOpacity="0.3" strokeWidth={2}
                  vectorEffect="non-scaling-stroke"/>
                {/* Filled core */}
                <circle cx={projLabel.x} cy={projLabel.y} r={R}
                  fill="#0B0B11" stroke="#FF1E00" strokeWidth={1.2}
                  vectorEffect="non-scaling-stroke"/>
                {/* Turn number */}
                <text x={projLabel.x} y={projLabel.y + FS * 0.35}
                  textAnchor="middle"
                  fontFamily="JetBrains Mono, monospace"
                  fontSize={FS}
                  fontWeight="800"
                  fill="#FF1E00"
                  paintOrder="stroke"
                  stroke="#0B0B11"
                  strokeWidth={0.5}
                >T{i + 1}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

window.IsoTrack = IsoTrack;
