export interface RaceWeekend {
  round_number: number;
  event_name: string;
  circuit_name: string;
  country: string;
  date: string;         // ISO date string
  session_type?: string;
}

export interface AvailableYearsResponse {
  years: number[];
}
