import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { telemetryAPI } from '../../services/api';
import TrackCanvas from './Track/TrackCanvas';
import Leaderboard from './UI/Leaderboard';
import WeatherPanel from './UI/WeatherPanel';
import Controls from './UI/Controls';
import ProgressBar from './UI/ProgressBar';
import SessionInfo from './UI/SessionInfo';
import { useRaceData } from './hooks/useRaceData';
import { usePlayback } from './hooks/usePlayback';
import type { TelemetryData } from '../../types/race.types';

const RaceReplay: React.FC = () => {
  const [searchParams] = useSearchParams();
  const year = parseInt(searchParams.get('year') || '2025');
  const round = parseInt(searchParams.get('round') || '1');
  const sessionType = searchParams.get('session') || 'R';

  const [telemetryData, setTelemetryData] = useState<TelemetryData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const { currentFrame, selectedDrivers } = useRaceData(telemetryData);
  const {
    frameIndex,
    paused,
    playbackSpeed,
    togglePause,
    changeSpeed,
    seek,
  } = usePlayback(telemetryData?.frames.length || 0);

  useEffect(() => {
    loadTelemetry();
  }, [year, round, sessionType]);

  const loadTelemetry = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await telemetryAPI.getRaceTelemetry(year, round, sessionType);
      setTelemetryData(data);
    } catch (err) {
      setError('Failed to load telemetry data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading race data...</div>;
  }

  if (error || !telemetryData) {
    return <div className="error">{error || 'No data available'}</div>;
  }

  return (
    <div className="race-replay">
      <SessionInfo sessionInfo={telemetryData.session_info} />

      <div className="race-replay__main">
        <div className="race-replay__track">
          <TrackCanvas
            telemetryData={telemetryData}
            frameIndex={frameIndex}
            selectedDrivers={selectedDrivers}
          />
        </div>

        <aside className="race-replay__sidebar">
          <Leaderboard
            currentFrame={currentFrame}
            driverColors={telemetryData.driver_colors}
            selectedDrivers={selectedDrivers}
          />
          <WeatherPanel weather={currentFrame?.weather} />
        </aside>
      </div>

      <ProgressBar
        totalFrames={telemetryData.frames.length}
        currentFrame={frameIndex}
        onSeek={seek}
      />

      <Controls
        paused={paused}
        playbackSpeed={playbackSpeed}
        onTogglePause={togglePause}
        onChangeSpeed={changeSpeed}
      />
    </div>
  );
};

export default RaceReplay;
