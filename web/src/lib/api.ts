import {
  ColumnarFrames,
  ReplayManifest,
  SeasonEventItem,
  SessionBuildStatus,
} from "@/types/replay";

export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  }
  // Empty string uses same-origin /api/* (proxied by Next.js to 127.0.0.1:8001 locally)
  return "";
}

async function parseJsonSafe<T>(res: Response, label: string): Promise<T> {
  const text = await res.text();
  if (!text || !text.trim()) {
    throw new Error(`Empty response received while loading ${label} (HTTP ${res.status}).`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    const preview = text.slice(0, 120).replace(/\s+/g, " ");
    throw new Error(
      `Invalid JSON while loading ${label} (HTTP ${res.status}, ${text.length} bytes): ${preview}`
    );
  }
}

export async function checkBackendHealth(): Promise<boolean> {
  const base = getApiBaseUrl();
  try {
    const res = await fetch(`${base}/api/health`, { cache: "no-store" });
    if (!res.ok) return false;
    const data = await res.json().catch(() => null);
    return data?.status === "ok";
  } catch {
    return false;
  }
}

export async function fetchDemoBundle(): Promise<{
  manifest: ReplayManifest;
  frames: ColumnarFrames;
  source: "api" | "static";
}> {
  const base = getApiBaseUrl();
  try {
    const [mRes, fRes] = await Promise.all([
      fetch(`${base}/api/sessions/demo/manifest`),
      fetch(`${base}/api/sessions/demo/frames`),
    ]);
    if (mRes.ok && fRes.ok) {
      const [manifest, frames] = await Promise.all([
        parseJsonSafe<ReplayManifest>(mRes, "demo manifest"),
        parseJsonSafe<ColumnarFrames>(fRes, "demo frames"),
      ]);
      return { manifest, frames, source: "api" };
    }
  } catch {
    // Fall through to built-in Vercel static demo assets
  }

  const [mStatic, fStatic] = await Promise.all([
    fetch("/demo/manifest.json"),
    fetch("/demo/frames.json"),
  ]);
  if (!mStatic.ok || !fStatic.ok) {
    throw new Error("Unable to load demo race bundle.");
  }
  const [manifest, frames] = await Promise.all([
    parseJsonSafe<ReplayManifest>(mStatic, "static demo manifest"),
    parseJsonSafe<ColumnarFrames>(fStatic, "static demo frames"),
  ]);
  return { manifest, frames, source: "static" };
}

export async function fetchSeasons(): Promise<{
  seasons: number[];
  default_year: number;
}> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/seasons`);
  if (!res.ok) throw new Error(`Failed to fetch seasons (${res.status})`);
  return parseJsonSafe(res, "seasons");
}

export async function fetchSeasonSchedule(year: number): Promise<SeasonEventItem[]> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/seasons/${year}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to load ${year} schedule`);
  }
  const data = await parseJsonSafe<{ events: SeasonEventItem[] }>(
    res,
    `${year} schedule`
  );
  return data.events;
}

export async function prepareSessionBundle(
  year: number,
  round: number,
  sessionType: string
): Promise<SessionBuildStatus> {
  const base = getApiBaseUrl();
  const res = await fetch(
    `${base}/api/sessions/${year}/${round}/${sessionType}/prepare`,
    { method: "POST" }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to start session telemetry build");
  }
  return parseJsonSafe(res, "prepare status");
}

export async function pollSessionStatus(
  year: number,
  round: number,
  sessionType: string
): Promise<SessionBuildStatus> {
  const base = getApiBaseUrl();
  const res = await fetch(
    `${base}/api/sessions/${year}/${round}/${sessionType}/status`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`Failed to check session status (HTTP ${res.status})`);
  return parseJsonSafe(res, "session status");
}

export async function fetchSessionBundle(
  year: number,
  round: number,
  sessionType: string
): Promise<{ manifest: ReplayManifest; frames: ColumnarFrames }> {
  const base = getApiBaseUrl();
  const [mRes, fRes] = await Promise.all([
    fetch(`${base}/api/sessions/${year}/${round}/${sessionType}/manifest`),
    fetch(`${base}/api/sessions/${year}/${round}/${sessionType}/frames`),
  ]);
  if (!mRes.ok || !fRes.ok) {
    throw new Error(
      `Failed to download session bundle (manifest HTTP ${mRes.status}, frames HTTP ${fRes.status}).`
    );
  }
  const [manifest, frames] = await Promise.all([
    parseJsonSafe<ReplayManifest>(mRes, "session manifest"),
    parseJsonSafe<ColumnarFrames>(fRes, "session frames"),
  ]);
  return { manifest, frames };
}
