const LiveCtx = React.createContext(null);
function LiveProvider({ children }) {
  const [snapshot, setSnap] = React.useState(null);
  const [frame, setFrame]   = React.useState(null);
  const [rc, setRc]         = React.useState([]);
  const [playback, setPb]   = React.useState({ speed: 1, is_paused: false });
  const [loading, setLoading] = React.useState({ status: "loading", progress: 0 });
  const [trackStatuses, setTrackStatuses] = React.useState([]);

  React.useEffect(() => {
    const h = window.APEX_CLIENT.openSocket((msg) => {
      if (msg.type === "loading") {
        setLoading({ status: msg.status || "loading", progress: msg.progress || 0, message: msg.message });
      } else if (msg.type === "snapshot" || msg.type === "reset") {
        setLoading({ status: "ready", progress: 100 });
        setSnap(msg);
        window.__LIVE_SNAPSHOT = msg;
        setRc([...(msg.race_control_history || [])].reverse());
        if (msg.track_statuses) setTrackStatuses(msg.track_statuses);
        if (msg.playback) setPb(msg.playback);
        // Install snapshot data into APEX shim (colors, driver meta)
        if (window.APEX?._installSnapshot) window.APEX._installSnapshot(msg);
        // Also treat snapshot as first frame
        if (msg.standings?.length) {
          const snapT = msg.t_seconds ?? (msg.frame_index || 0);
          const snapClockH = Math.floor(snapT / 3600);
          const snapClockM = Math.floor((snapT % 3600) / 60);
          const snapClockS = Math.floor(snapT % 60);
          const snapClock = `${String(snapClockH).padStart(2,"0")}:${String(snapClockM).padStart(2,"0")}:${String(snapClockS).padStart(2,"0")}`;
          const snapFrame = {
            type: "frame",
            frame_index: msg.frame_index || 0,
            total_frames: msg.total_frames || 1,
            t: 0,
            t_seconds: snapT,
            lap: msg.standings[0]?.lap || 1,
            total_laps: msg.total_laps || 1,
            clock: snapClock,
            track_status: "1",
            flag_state: msg.flag_state || "green",
            playback_speed: msg.playback?.speed || 1,
            is_paused: msg.playback?.is_paused ?? true,
            weather: msg.weather ?? {},
            safety_car: null,
            standings: msg.standings,
            new_rc_events: [],
          };
          window.__LIVE_FRAME = snapFrame;
          if (window.APEX?._accumulateFrame) window.APEX._accumulateFrame(snapFrame);
          setFrame(snapFrame);
        }
      } else if (msg.type === "frame") {
        window.__LIVE_FRAME = msg;
        if (window.APEX?._accumulateFrame) window.APEX._accumulateFrame(msg);
        setFrame(msg);
        setPb((p) => ({ ...p, speed: msg.playback_speed, is_paused: msg.is_paused }));
        if (msg.new_rc_events?.length) {
          setRc((prev) => [...msg.new_rc_events.slice().reverse(), ...prev]);
        }
      }
    });
    return () => h.close();
  }, []);

  return <LiveCtx.Provider value={{ snapshot, frame, rc, playback, setPb, loading, trackStatuses }}>{children}</LiveCtx.Provider>;
}
const useLive = () => React.useContext(LiveCtx);
window.LIVE = { LiveProvider, useLive };
