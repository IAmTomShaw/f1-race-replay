/**
 * Hotkey handler logic for App.jsx.
 * Extracted for testability — the handler reads from a refs bag so it never
 * closes over stale state, and it guards against key-repeat spam.
 */

const SPEED_STEPS = [0.5, 1, 2, 4];

function buildHotkeyHandler(refs, post, togglePlay, seekRemote, setSpeedRemote, setShowDRS, setShowLabels, setShowProgress, setViewMode) {
  return (e) => {
    if (e.repeat) return;
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;

    const { t, speed, isPaused } = refs;

    if (e.code === "Space") {
      e.preventDefault();
      if (isPaused.current) post("/api/playback/play");
      else post("/api/playback/pause");
    } else if (e.code === "ArrowLeft") {
      seekRemote(Math.max(0, t.current - (e.shiftKey ? 0.05 : 0.01)));
    } else if (e.code === "ArrowRight") {
      seekRemote(Math.min(1, t.current + (e.shiftKey ? 0.05 : 0.01)));
    } else if (e.code === "ArrowUp") {
      const idx = SPEED_STEPS.indexOf(speed.current);
      setSpeedRemote(SPEED_STEPS[Math.min(idx + 1, SPEED_STEPS.length - 1)]);
    } else if (e.code === "ArrowDown") {
      const idx = SPEED_STEPS.indexOf(speed.current);
      setSpeedRemote(SPEED_STEPS[Math.max(idx - 1, 0)]);
    } else if (e.key === "1") {
      setSpeedRemote(0.5);
    } else if (e.key === "2") {
      setSpeedRemote(1);
    } else if (e.key === "3") {
      setSpeedRemote(2);
    } else if (e.key === "4") {
      setSpeedRemote(4);
    } else if (e.key === "d" || e.key === "D") {
      setShowDRS(v => !v);
    } else if (e.key === "l" || e.key === "L") {
      setShowLabels(v => !v);
    } else if (e.key === "b" || e.key === "B") {
      setShowProgress(v => !v);
    } else if (e.key === "r" || e.key === "R") {
      seekRemote(0);
    } else if (e.key === "m" || e.key === "M") {
      if (setViewMode) setViewMode((v) => (v === "top" ? "iso" : "top"));
    }
  };
}

window.APEX_HOTKEY = { buildHotkeyHandler, SPEED_STEPS };
