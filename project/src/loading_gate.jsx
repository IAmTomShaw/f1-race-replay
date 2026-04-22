function LoadingGate({ children }) {
  const { loading } = window.LIVE.useLive();
  const [poll, setPoll] = React.useState(null);
  const [dataReady, setDataReady] = React.useState(false);

  // Wait for APEX bootstrap data (summary + geometry fetch)
  React.useEffect(() => {
    if (window.APEX_DATA_READY) {
      window.APEX_DATA_READY.then(() => setDataReady(true));
    } else {
      setDataReady(true); // legacy path if promise not present
    }
  }, []);

  // Poll /api/session/status as belt-and-braces for the WS loading pings.
  React.useEffect(() => {
    if (loading?.status === "ready") return;
    let alive = true;
    const tick = async () => {
      if (!alive) return;
      try {
        const s = await window.APEX_CLIENT.get("/api/session/status");
        if (alive) setPoll(s);
      } catch {}
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, [loading?.status]);

  const status = loading?.status || poll?.status || "loading";
  const progress = Math.max(loading?.progress || 0, poll?.progress || 0);
  if (status === "ready" && dataReady) return children;
  return (
    <>
      {children}
      <div style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)",
        color: "#fff", display: "flex", alignItems: "center",
        justifyContent: "center", flexDirection: "column", zIndex: 9999,
        fontFamily: "monospace",
      }}>
        <div style={{ fontSize: 14, letterSpacing: 3, marginBottom: 12 }}>LOADING SESSION</div>
        <div style={{ width: 320, height: 4, background: "#333" }}>
          <div style={{ width: `${progress}%`, height: "100%", background: "#FF1E00", transition: "width 0.3s" }} />
        </div>
        <div style={{ marginTop: 10, fontSize: 11, opacity: 0.7 }}>{poll?.message || loading?.message || "..."}</div>
      </div>
    </>
  );
}
window.LOADING_GATE = LoadingGate;
