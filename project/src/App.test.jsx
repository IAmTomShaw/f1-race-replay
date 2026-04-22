import { describe, it, expect, vi, beforeEach } from "vitest";

// hotkeyHandler.js assigns to window.APEX_HOTKEY — import side-effects only
import "./hotkeyHandler.js";
const { buildHotkeyHandler, SPEED_STEPS } = window.APEX_HOTKEY;

// ── Helpers ──

function makeRefs(t = 0.5, speed = 1, isPaused = true) {
  return {
    t: { current: t },
    speed: { current: speed },
    isPaused: { current: isPaused },
  };
}

function makeMocks() {
  return {
    post: vi.fn(),
    togglePlay: vi.fn(),
    seekRemote: vi.fn(),
    setSpeedRemote: vi.fn(),
    setShowDRS: vi.fn(),
    setShowLabels: vi.fn(),
    setShowProgress: vi.fn(),
  };
}

function makeHandler(refs, mocks) {
  return buildHotkeyHandler(
    refs,
    mocks.post,
    mocks.togglePlay,
    mocks.seekRemote,
    mocks.setSpeedRemote,
    mocks.setShowDRS,
    mocks.setShowLabels,
    mocks.setShowProgress,
  );
}

/** Create a fake KeyboardEvent-like object. */
function fakeKey(code, opts = {}) {
  return {
    code,
    key: opts.key ?? code,
    repeat: opts.repeat ?? false,
    shiftKey: opts.shiftKey ?? false,
    target: opts.target ?? { tagName: "DIV" },
    preventDefault: vi.fn(),
  };
}

// ── Tests ──

describe("hotkeyHandler", () => {
  let refs, mocks, handler;

  beforeEach(() => {
    refs = makeRefs();
    mocks = makeMocks();
    handler = makeHandler(refs, mocks);
  });

  // ──────────────────────────────────────────────────────────────
  // Bug 1: Handler reads from refs (not stale closures)
  // ──────────────────────────────────────────────────────────────
  describe("Bug 1: ref-based reads (no stale closure)", () => {
    it("reads current speed from ref after it changes", () => {
      refs.speed.current = 2;
      handler(fakeKey("ArrowUp"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(4);
    });

    it("reads current t from ref after it changes", () => {
      refs.t.current = 0.9;
      handler(fakeKey("ArrowRight"));
      expect(mocks.seekRemote).toHaveBeenCalledWith(Math.min(1, 0.9 + 0.01));
    });

    it("reads current isPaused from ref after it changes", () => {
      refs.isPaused.current = false;
      handler(fakeKey("Space"));
      expect(mocks.post).toHaveBeenCalledWith("/api/playback/pause");
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Bug 2: ArrowUp / ArrowDown speed step logic
  // ──────────────────────────────────────────────────────────────
  describe("Bug 2: speed step logic", () => {
    it("ArrowUp from 0.5 → 1", () => {
      refs.speed.current = 0.5;
      handler(fakeKey("ArrowUp"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(1);
    });

    it("ArrowUp from 1 → 2", () => {
      refs.speed.current = 1;
      handler(fakeKey("ArrowUp"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(2);
    });

    it("ArrowUp from 2 → 4", () => {
      refs.speed.current = 2;
      handler(fakeKey("ArrowUp"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(4);
    });

    it("ArrowUp from 4 → 4 (clamped at max)", () => {
      refs.speed.current = 4;
      handler(fakeKey("ArrowUp"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(4);
    });

    it("ArrowDown from 4 → 2", () => {
      refs.speed.current = 4;
      handler(fakeKey("ArrowDown"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(2);
    });

    it("ArrowDown from 2 → 1", () => {
      refs.speed.current = 2;
      handler(fakeKey("ArrowDown"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(1);
    });

    it("ArrowDown from 1 → 0.5", () => {
      refs.speed.current = 1;
      handler(fakeKey("ArrowDown"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(0.5);
    });

    it("ArrowDown from 0.5 → 0.5 (clamped at min)", () => {
      refs.speed.current = 0.5;
      handler(fakeKey("ArrowDown"));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(0.5);
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Bug 3: key repeat spam
  // ──────────────────────────────────────────────────────────────
  describe("Bug 3: repeat key suppression", () => {
    it("ignores repeat ArrowUp", () => {
      handler(fakeKey("ArrowUp", { repeat: true }));
      expect(mocks.setSpeedRemote).not.toHaveBeenCalled();
    });

    it("ignores repeat ArrowDown", () => {
      handler(fakeKey("ArrowDown", { repeat: true }));
      expect(mocks.setSpeedRemote).not.toHaveBeenCalled();
    });

    it("ignores repeat ArrowLeft", () => {
      handler(fakeKey("ArrowLeft", { repeat: true }));
      expect(mocks.seekRemote).not.toHaveBeenCalled();
    });

    it("ignores repeat ArrowRight", () => {
      handler(fakeKey("ArrowRight", { repeat: true }));
      expect(mocks.seekRemote).not.toHaveBeenCalled();
    });

    it("ignores repeat Space", () => {
      handler(fakeKey("Space", { repeat: true }));
      expect(mocks.post).not.toHaveBeenCalled();
      expect(mocks.togglePlay).not.toHaveBeenCalled();
    });

    it("processes non-repeat ArrowUp normally", () => {
      refs.speed.current = 1;
      handler(fakeKey("ArrowUp", { repeat: false }));
      expect(mocks.setSpeedRemote).toHaveBeenCalledWith(2);
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Additional: input focus guard
  // ──────────────────────────────────────────────────────────────
  describe("input focus guard", () => {
    it("ignores keys when an INPUT is focused", () => {
      handler(fakeKey("Space", { target: { tagName: "INPUT" } }));
      expect(mocks.post).not.toHaveBeenCalled();
    });

    it("ignores keys when a TEXTAREA is focused", () => {
      handler(fakeKey("Space", { target: { tagName: "TEXTAREA" } }));
      expect(mocks.post).not.toHaveBeenCalled();
    });
  });
});
