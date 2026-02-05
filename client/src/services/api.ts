import axios from 'axios';
import type { RaceWeekend, TelemetryData } from '../types/race.types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

export const racesAPI = {
  getSchedule: async (year: number): Promise<RaceWeekend[]> => {
    const response = await api.get(`/api/races/schedule/${year}`);
    return response.data;
  },

  getAvailableYears: async (): Promise<number[]> => {
    const response = await api.get('/api/races/available-years');
    return response.data.years;
  },
};

export const telemetryAPI = {
  getRaceTelemetry: async (
    year: number,
    round: number,
    sessionType: string = 'R'
  ): Promise<TelemetryData> => {
    const response = await api.get(`/api/telemetry/race/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getTelemetryStatus: async (
    year: number,
    round: number,
    sessionType: string = 'R'
  ) => {
    const response = await api.get(`/api/telemetry/status/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },
};

export default api;
