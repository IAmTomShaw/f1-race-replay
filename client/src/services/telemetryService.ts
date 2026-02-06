import api from './api';
import type { RaceFramesResponse, RawTelemetryData } from '../types/api.types';
import type { TrackDataResponse } from '../types/track-api.types';

export const telemetryService = {
  /**
   * Get full race telemetry data (heavy - all laps)
   */
  getRaceTelemetry: async (
    year: number,
    round: number,
    sessionType: string = 'R'
  ): Promise<RawTelemetryData> => {
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

  getSessionInfo: async (
    year: number,
    round: number,
    sessionType: string = 'R'
  ) => {
    const response = await api.get(`/api/sessions/info/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getTrackData: async (
    year: number,
    round: number,
    sessionType: string = 'R'
  ): Promise<TrackDataResponse> => {
    const response = await api.get(`/api/telemetry/track/${year}/${round}`, {
      params: { session_type: sessionType },
    });
    return response.data;
  },

  getRaceFrames: async (
    year: number,
    round: number,
    sessionType: string = 'R',
    maxFrames: number = 5000
  ): Promise<RaceFramesResponse> => {
    const response = await api.get(`/api/telemetry/frames/${year}/${round}`, {
      params: { 
        session_type: sessionType,
        max_frames: maxFrames
      },
    });
    return response.data;
  },
};
