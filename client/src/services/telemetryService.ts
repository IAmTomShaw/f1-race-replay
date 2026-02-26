import api from './api';
import type { RaceFramesResponse, RawTelemetryData } from '../types/api.types';
import type { TrackDataResponse } from '../types/track-api.types';
import type { RaceWeekend, AvailableYearsResponse } from '../types/race.types';

export const telemetryService = {
  getRaceTelemetry: async (
    year: number, round: number, sessionType = 'R'
  ): Promise<RawTelemetryData> => {
    const response = await api.get(`/api/telemetry/race/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getTelemetryStatus: async (year: number, round: number, sessionType = 'R') => {
    const response = await api.get(`/api/telemetry/status/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getSessionInfo: async (year: number, round: number, sessionType = 'R') => {
    const response = await api.get(`/api/sessions/info/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getTrackData: async (
    year: number, round: number, sessionType = 'R'
  ): Promise<TrackDataResponse> => {
    const response = await api.get(`/api/telemetry/track/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getRaceFrames: async (
    year: number, round: number, sessionType = 'R', maxFrames = 5000
  ): Promise<RaceFramesResponse> => {
    const response = await api.get(`/api/telemetry/frames/${year}/${round}`, {
      params: { session_type: sessionType, max_frames: maxFrames },
    });
    return response.data;
  },

  // ── Schedule endpoints ──────────────────────────────────────────────────

  getAvailableYears: async (): Promise<AvailableYearsResponse> => {
    const response = await api.get('/api/races/available-years');
    return response.data;
  },

  getRaceSchedule: async (year: number): Promise<RaceWeekend[]> => {
    const response = await api.get(`/api/races/schedule/${year}`);
    return response.data;
  },
};
