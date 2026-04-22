// Single source of truth for every user-togglable panel.
// Used by PanelsMenu and by App to thread layout state through.

window.PANEL_REGISTRY = [
  { id: "leaderboard",  title: "CLASSIFICATION" },
  { id: "track",        title: "CIRCUIT VIEW" },
  { id: "strategy",     title: "STRATEGY" },
  { id: "compare",      title: "COMPARE TRACES" },
  { id: "sectors",      title: "SECTOR TIMES" },
  { id: "feed",         title: "RACE CONTROL" },
  { id: "driverCard",   title: "PRIMARY DRIVER" },
  { id: "driverCard2",  title: "COMPARE DRIVER" },
  { id: "gap",          title: "GAP VISUALIZATION" },
];
