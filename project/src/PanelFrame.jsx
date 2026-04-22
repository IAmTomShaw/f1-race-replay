// PanelFrame — Tier 1 panel chrome (collapse / maximize / close).
//
// Wraps any panel body in a slot that adds a tiny button strip in the
// top-right corner. No visual chrome of its own, so panels that already
// draw their own border/background render unchanged.
//
// Collapsed: slot shrinks to a thin title bar.
// Maximized: portals the body into a full-center overlay.
// Hidden:    slot renders nothing; user restores via the Panels menu.

const PANEL_LAYOUT_KEY = "apex.panelLayout.v1";

function loadLayout() {
  try {
    const raw = localStorage.getItem(PANEL_LAYOUT_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveLayout(layout) {
  try { localStorage.setItem(PANEL_LAYOUT_KEY, JSON.stringify(layout)); }
  catch { /* ignore quota/private-mode errors */ }
}

function defaultState() {
  return { visible: true, collapsed: false };
}

function useLayout() {
  const [layout, setLayout] = React.useState(loadLayout);
  const [maximized, setMaximized] = React.useState(null);

  React.useEffect(() => { saveLayout(layout); }, [layout]);

  // Esc exits maximize
  React.useEffect(() => {
    if (!maximized) return;
    const onKey = (e) => { if (e.key === "Escape") setMaximized(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [maximized]);

  const getState = React.useCallback((id) => ({ ...defaultState(), ...(layout[id] || {}) }), [layout]);
  const update = React.useCallback((id, patch) => {
    setLayout((prev) => ({ ...prev, [id]: { ...defaultState(), ...(prev[id] || {}), ...patch } }));
  }, []);

  return {
    getState,
    setVisible: (id, visible) => update(id, { visible }),
    setCollapsed: (id, collapsed) => update(id, { collapsed }),
    toggleCollapsed: (id) => update(id, { collapsed: !getState(id).collapsed }),
    maximized,
    setMaximized,
  };
}

function IconButton({ onClick, title, children }) {
  const [h, setH] = React.useState(false);
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(e); }}
      onMouseDown={(e) => e.stopPropagation()}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      title={title}
      style={{
        width: 16, height: 16, padding: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: h ? "rgba(255,30,0,0.25)" : "rgba(11,11,17,0.55)",
        border: "1px solid rgba(255,255,255,0.1)",
        color: "#E6E6EF", cursor: "pointer",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10, lineHeight: 1,
      }}>
      {children}
    </button>
  );
}

function PanelButtons({ id, title, collapsed, onCollapse, onMaximize, onClose, isMaximized, buttonStyle }) {
  return (
    <div style={{
      position: "absolute",
      top: 6, right: 6,
      display: "flex", gap: 3,
      zIndex: 4,
      ...(buttonStyle || {}),
    }}>
      <IconButton onClick={onCollapse} title={collapsed ? "Expand" : "Collapse"}>
        {collapsed ? "▸" : "▾"}
      </IconButton>
      <IconButton onClick={onMaximize} title={isMaximized ? "Restore" : "Maximize"}>
        {isMaximized ? "▭" : "⛶"}
      </IconButton>
      <IconButton onClick={onClose} title="Hide panel">✕</IconButton>
    </div>
  );
}

function CollapsedStub({ title, onExpand }) {
  return (
    <div
      onClick={onExpand}
      style={{
        height: 28,
        display: "flex", alignItems: "center",
        padding: "0 10px",
        background: "linear-gradient(180deg, rgba(20,20,30,0.92), rgba(11,11,17,0.94))",
        border: "1px solid rgba(255,255,255,0.06)",
        cursor: "pointer",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10, letterSpacing: "0.16em",
        color: "rgba(180,180,200,0.7)",
      }}>
      <span style={{ flex: 1 }}>{title}</span>
      <span style={{ opacity: 0.6 }}>▸</span>
    </div>
  );
}

// PanelSlot wraps a panel in a relative container and overlays the button strip.
// Pass `style` to control the slot's flex/grid behavior.
function PanelSlot({ id, title, layout, style, buttonStyle, children }) {
  const state = layout.getState(id);
  if (!state.visible) return null;

  const isMaximized = layout.maximized === id;
  // While maximized, keep the slot in place but show a placeholder so grid doesn't collapse.
  if (isMaximized) {
    return (
      <div style={{ ...style, position: "relative" }}>
        <div style={{
          height: "100%",
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(11,11,17,0.4)",
          border: "1px dashed rgba(255,30,0,0.3)",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9, letterSpacing: "0.18em",
          color: "rgba(180,180,200,0.5)",
        }}>
          {title} · MAXIMIZED
        </div>
      </div>
    );
  }

  if (state.collapsed) {
    return (
      <div style={{ ...style, flex: "none" }}>
        <CollapsedStub title={title} onExpand={() => layout.setCollapsed(id, false)} />
      </div>
    );
  }

  return (
    <div style={{ ...style, position: "relative" }}>
      {children}
      <PanelButtons
        id={id}
        title={title}
        collapsed={false}
        isMaximized={false}
        onCollapse={() => layout.setCollapsed(id, true)}
        onMaximize={() => layout.setMaximized(id)}
        onClose={() => layout.setVisible(id, false)}
        buttonStyle={buttonStyle}
      />
    </div>
  );
}

// MaximizedOverlay renders the currently-maximized panel full-size in the main area.
// Placed inside the main grid cell by App so it covers exactly the layout region.
function MaximizedOverlay({ layout, title, children }) {
  if (!layout.maximized) return null;
  return (
    <div style={{
      position: "absolute", inset: 0,
      background: "rgba(5,5,10,0.92)",
      backdropFilter: "blur(4px)",
      zIndex: 20,
      display: "flex", flexDirection: "column",
      padding: 10,
    }}>
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        {children}
        <PanelButtons
          title={title}
          collapsed={false}
          isMaximized={true}
          onCollapse={() => { layout.setMaximized(null); layout.setCollapsed(layout.maximized, true); }}
          onMaximize={() => layout.setMaximized(null)}
          onClose={() => { layout.setVisible(layout.maximized, false); layout.setMaximized(null); }}
        />
      </div>
    </div>
  );
}

// PanelsMenu — dropdown listing every registered panel with a visibility checkbox.
function PanelsMenu({ layout, registry }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    window.addEventListener("mousedown", onDoc);
    return () => window.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          padding: "4px 10px",
          background: open ? "rgba(255,30,0,0.2)" : "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.1)",
          color: "#E6E6EF", cursor: "pointer",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10, letterSpacing: "0.14em", fontWeight: 700,
        }}>
        PANELS ▾
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", right: 0, marginTop: 4,
          minWidth: 200,
          background: "linear-gradient(180deg, rgba(20,20,30,0.98), rgba(11,11,17,0.98))",
          border: "1px solid rgba(255,30,0,0.3)",
          padding: 6,
          zIndex: 30,
          fontFamily: "JetBrains Mono, monospace",
          boxShadow: "0 10px 30px rgba(0,0,0,0.6)",
        }}>
          <div style={{ fontSize: 8, color: "rgba(180,180,200,0.5)", letterSpacing: "0.2em", padding: "4px 6px 6px" }}>
            VISIBLE PANELS
          </div>
          {registry.map((p) => {
            const state = layout.getState(p.id);
            return (
              <label key={p.id} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "4px 6px",
                fontSize: 10, letterSpacing: "0.08em",
                color: state.visible ? "#E6E6EF" : "rgba(180,180,200,0.55)",
                cursor: "pointer",
              }}>
                <input
                  type="checkbox"
                  checked={state.visible}
                  onChange={(e) => layout.setVisible(p.id, e.target.checked)}
                  style={{ accentColor: "#FF1E00" }}
                />
                <span style={{ flex: 1 }}>{p.title}</span>
                {state.collapsed && state.visible && (
                  <span style={{ fontSize: 8, color: "rgba(180,180,200,0.5)" }}>COLLAPSED</span>
                )}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

window.PanelSlot = PanelSlot;
window.PanelsMenu = PanelsMenu;
window.MaximizedOverlay = MaximizedOverlay;
window.useLayout = useLayout;
