// Map team names to logo file names or colors
export const TEAM_INFO: Record<string, { logo?: string; color: string; shortName: string }> = {
  'Red Bull Racing': { color: '#3671C6', shortName: 'RBR', logo: 'Red Bull Racing.png' },
  'Mercedes': { color: '#27F4D2', shortName: 'MER', logo: 'Mercedes.png' },
  'Ferrari': { color: '#E8002D', shortName: 'FER', logo: 'Ferrari.png' },
  'McLaren': { color: '#FF8000', shortName: 'MCL', logo: 'McLaren.png' },
  'Aston Martin': { color: '#229971', shortName: 'AST', logo: 'Aston Martin.png' },
  'Alpine': { color: '#FF87BC', shortName: 'ALP', logo: 'Alpine.png' },
  'Williams': { color: '#64C4FF', shortName: 'WIL', logo: 'Williams.png' },
  'Haas F1 Team': { color: '#B6BABD', shortName: 'HAA', logo: 'Haas.png' },
  'RB': { color: '#6692FF', shortName: 'RB', logo: 'Alpha Tauri.png' },
  'Racing Bulls': { color: '#6692FF', shortName: 'RB', logo: 'Alpha Tauri.png' },
  'Sauber': { color: '#52E252', shortName: 'SAU', logo: 'Sauber.png' },
  'Kick Sauber': { color: '#52E252', shortName: 'SAU', logo: 'Kick Sauber.png' },
};

export function getTeamLogo(teamName: string): string | null {
  const team = TEAM_INFO[teamName];
  //console.log(`Looking up logo for team: ${teamName}, found: ${team?.logo}`);
  return team?.logo ? `${team.logo}` : null;
}

export function getTeamShortName(teamName: string): string {
  const team = TEAM_INFO[teamName];
  return team?.shortName || teamName.substring(0, 3).toUpperCase();
}
