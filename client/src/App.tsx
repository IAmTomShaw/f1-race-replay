import { useState, useEffect, useRef } from 'react';
import AnimatedTrackCanvas from './components/Track/AnimatedTrackCanvas';
import { telemetryService } from './services/telemetryService';
import { buildTrackFromFrames } from './utils/trackDataConverter';
import type { TrackData } from './types/track.types';
import type { Frame } from './types/api.types';
import './App.css';

function App() {
  const [trackData, setTrackData] = useState<TrackData | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [driverColors, setDriverColors] = useState<Record<string, [number, number, number]>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionInfo, setSessionInfo] = useState<string>('');
  const [loadingTime, setLoadingTime] = useState<number>(0);

  const [year] = useState<number>(2024);
  const [round] = useState<number>(1);
  
  const loadingIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    loadRaceData();
  }, [year, round]);

  useEffect(() => {
    return () => {
      if (loadingIntervalRef.current) {
        clearInterval(loadingIntervalRef.current);
      }
    };
  }, []);

  const loadRaceData = async () => {
    setLoading(true);
    setError(null);
    setLoadingTime(0);
    
    const startTime = Date.now();
    loadingIntervalRef.current = window.setInterval(() => {
      setLoadingTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    
    try {
      console.log(`Loading race data for ${year} Round ${round}...`);
      
      // Load track shape
      const trackResponse = await telemetryService.getTrackData(year, round, 'R');
      console.log('Track data loaded:', trackResponse);
      
      const track = buildTrackFromFrames(trackResponse.frames, trackResponse.drs_zones);
      
      if (!track) {
        throw new Error('Failed to build track from frames');
      }

      setTrackData(track);
      setSessionInfo(
        `${trackResponse.session_info.event_name} - ${trackResponse.session_info.circuit_name}`
      );
      
      // Load race frames (5000 frames = ~3.3 minutes of race at 25fps)
      console.log('Loading race frames...');
      const framesResponse = await telemetryService.getRaceFrames(year, round, 'R', 5000);
      console.log(`Loaded ${framesResponse.frames.length} frames`);
      
      setFrames(framesResponse.frames);
      setDriverColors(framesResponse.driver_colors);
      
      console.log('✅ Race data loaded successfully!');
    } catch (err: any) {
      console.error('Error:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load race data');
    } finally {
      setLoading(false);
      if (loadingIntervalRef.current) {
        clearInterval(loadingIntervalRef.current);
        loadingIntervalRef.current = null;
      }
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>🏎️ F1 Race Replay</h1>
        <div className="session-info">
          {loading && (
            <p>
              Loading race data... ({loadingTime}s elapsed)
            </p>
          )}
          {error && <p className="error">Error: {error}</p>}
          {sessionInfo && !loading && <p>{sessionInfo}</p>}
        </div>
      </header>

      <main className="app-main">
        {loading ? (
          <div className="loading-spinner">
            <div className="spinner"></div>
            <p>Loading {year} Round {round}...</p>
            <p className="loading-time">{loadingTime} seconds elapsed</p>
          </div>
        ) : error ? (
          <div className="error-message">
            <h2>❌ Failed to Load Race</h2>
            <p>{error}</p>
            <button onClick={loadRaceData}>Retry</button>
          </div>
        ) : (
          <AnimatedTrackCanvas 
            trackData={trackData || undefined}
            frames={frames}
            driverColors={driverColors}
          />
        )}
      </main>

      <footer className="app-footer">
        <p>
          {year} Round {round} | 
          {trackData && ` Track: ✓`}
          {frames.length > 0 && ` | Frames: ${frames.length}`}
          {trackData?.drsZones && ` | DRS Zones: ${trackData.drsZones.length}`}
        </p>
      </footer>
    </div>
  );
}

export default App;
