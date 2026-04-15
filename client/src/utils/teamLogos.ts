/**
 * Static lookup table mapping official F1 team names to their display metadata.
 * Covers all teams present in the 2021–2024 era, including rebranded entries
 * (e.g. AlphaTauri → RB → Racing Bulls, Alfa Romeo → Sauber → Kick Sauber).
 *
 * @property {string} [logo] - Filename of the team logo asset (resolved via `teamLogoUrl`).
 * @property {string} color - Hex color string representing the team's primary livery color.
 * @property {string} shortName - Three-letter abbreviation used in compact UI contexts.
 */
export const TEAM_INFO: Record<string, { logo?: string; color: string; shortName: string }> = {
  'Red Bull Racing': { color: '#3671C6', shortName: 'RBR', logo: 'Red Bull Racing.png' },
  'Mercedes':        { color: '#27F4D2', shortName: 'MER', logo: 'Mercedes.png' },
  'Ferrari':         { color: '#E8002D', shortName: 'FER', logo: 'Ferrari.png' },
  'McLaren':         { color: '#FF8000', shortName: 'MCL', logo: 'McLaren.png' },
  'Aston Martin':    { color: '#229971', shortName: 'AST', logo: 'Aston Martin.png' },
  'Alpine':          { color: '#FF87BC', shortName: 'ALP', logo: 'Alpine.png' },
  'Williams':        { color: '#64C4FF', shortName: 'WIL', logo: 'Williams.png' },
  'Haas F1 Team':    { color: '#B6BABD', shortName: 'HAA', logo: 'Haas.png' },
  'RB':              { color: '#6692FF', shortName: 'RB',  logo: 'Alpha Tauri.png' },
  'Racing Bulls':    { color: '#6692FF', shortName: 'RB',  logo: 'Alpha Tauri.png' },
  'AlphaTauri':      { color: '#6692FF', shortName: 'AT',  logo: 'Alpha Tauri.png' },
  'Sauber':          { color: '#52E252', shortName: 'SAU', logo: 'Sauber.png' },
  'Kick Sauber':     { color: '#52E252', shortName: 'SAU', logo: 'Kick Sauber.png' },
  'Alfa Romeo':      { color: '#B6BABD', shortName: 'AR',  logo: 'Alfa Romeo.png' },
};

/**
 * Returns the logo filename for a given team name, or null when no entry exists.
 * The filename should be passed to `teamLogoUrl` from `lib/assets` to resolve
 * a fully qualified URL.
 *
 * @param {string} teamName - The full official team name (e.g. `"Red Bull Racing"`).
 * @returns {string | null} Logo filename (e.g. `"Ferrari.png"`), or null for unknown teams.
 */
export function getTeamLogo(teamName: string): string | null {
  const team = TEAM_INFO[teamName];
  return team?.logo ? `${team.logo}` : null;
}

/**
 * Returns the three-letter short name for a given team. Falls back to the first
 * three characters of the team name (uppercased) when no entry exists in `TEAM_INFO`,
 * so callers always receive a non-empty string.
 *
 * @param {string} teamName - The full official team name (e.g. `"Aston Martin"`).
 * @returns {string} Three-letter short name (e.g. `"AST"`), or a generated fallback.
 */
export function getTeamShortName(teamName: string): string {
  const team = TEAM_INFO[teamName];
  return team?.shortName || teamName.substring(0, 3).toUpperCase();
}
