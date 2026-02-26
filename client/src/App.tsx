import { useState, useEffect, useRef } from 'react';
import Navbar from './components/Dashboard/Navbar';
import RaceViewer from './components/Dashboard/RaceViewer';
import RaceSelect from './components/RaceSelect';
import { telemetryService } from './services/telemetryService';
import { buildTrackFromFrames } from './utils/trackDataConverter';
import type { TrackData } from './types/track.types';
import type { Frame } from './types/api.types';
import './styles/variables.css';
import './App.css';

type Screen = 'select' | 'viewer';

interface RaceRef { year: number; round: number; }

function App() {
  const [screen, setScreen] = useState<Screen>('select');

  const [selectedYear, setSelectedYear] = useState<number>(2024);
  const [selectedRound, setSelectedRound] = useState<number>(1);

  // Flat ordered list of all races across all seasons, built when the user
  // enters the viewer so prev/next navigation can wrap across year boundaries.
  const [allRaces, setAllRaces] = useState<RaceRef[]>([]);

  const [trackData, setTrackData] = useState<TrackData | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [driverColors, setDriverColors] = useState<Record<string, [number, number, number]>>({});
  const [driverTeams, setDriverTeams] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingTime, setLoadingTime] = useState(0);
  const [eventName, setEventName] = useState('');
  const [circuitName, setCircuitName] = useState('');
  const [country, setCountry] = useState('');

  const loadingIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (loadingIntervalRef.current) clearInterval(loadingIntervalRef.current);
    };
  }, []);

  // Build the flat cross-season race list once when transitioning to the viewer.
  const buildAllRaces = async (currentYear: number, currentRound: number) => {
    try {
      const { years } = await telemetryService.getAvailableYears();
      const sorted = [...years].sort((a, b) => a - b);

      const schedules = await Promise.all(
        sorted.map(y => telemetryService.getRaceSchedule(y).then(races =>
          races.map(r => ({ year: y, round: r.round_number }))
        ).catch(() => [] as RaceRef[]))
      );

      setAllRaces(schedules.flat());
    } catch {
      // Fall back to just the current year's rounds being navigable
      try {
        const races = await telemetryService.getRaceSchedule(currentYear);
        setAllRaces(races.map(r => ({ year: currentYear, round: r.round_number })));
      } catch {
        setAllRaces([{ year: currentYear, round: currentRound }]);
      }
    }
  };

  const handleSelectRace = (year: number, round: number) => {
    setSelectedYear(year);
    setSelectedRound(round);
    setScreen('viewer');
    buildAllRaces(year, round);
    loadRaceData(year, round);
  };

  const handleGoHome = () => {
    setTrackData(null);
    setFrames([]);
    setError(null);
    setAllRaces([]);
    setScreen('select');
  };

  const loadRaceData = async (year: number, round: number) => {
    setLoading(true);
    setError(null);
    setLoadingTime(0);
    setTrackData(null);
    setFrames([]);

    const startTime = Date.now();
    loadingIntervalRef.current = window.setInterval(() => {
      setLoadingTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const trackResponse = await telemetryService.getTrackData(year, round, 'R');
      const track = buildTrackFromFrames(trackResponse.frames, trackResponse.drs_zones);
      if (!track) throw new Error('Failed to build track');

      setTrackData(track);
      setEventName(trackResponse.session_info.event_name);
      setCircuitName(trackResponse.session_info.circuit_name);
      setCountry(trackResponse.session_info.country);

      const framesResponse = await telemetryService.getRaceFrames(year, round, 'R', 5000);
      setFrames(framesResponse.frames);
      setDriverColors(framesResponse.driver_colors);
      setDriverTeams(framesResponse.driver_teams || {});
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load');
    } finally {
      setLoading(false);
      if (loadingIntervalRef.current) {
        clearInterval(loadingIntervalRef.current);
        loadingIntervalRef.current = null;
      }
    }
  };

  const currentRaceIdx = allRaces.findIndex(
    r => r.year === selectedYear && r.round === selectedRound
  );

  const handlePrevRace = () => {
    if (currentRaceIdx <= 0) return;
    const { year, round } = allRaces[currentRaceIdx - 1];
    setSelectedYear(year);
    setSelectedRound(round);
    loadRaceData(year, round);
  };

  const handleNextRace = () => {
    if (currentRaceIdx < 0 || currentRaceIdx >= allRaces.length - 1) return;
    const { year, round } = allRaces[currentRaceIdx + 1];
    setSelectedYear(year);
    setSelectedRound(round);
    loadRaceData(year, round);
  };

  return (
    <div className="app">
      <main className="app-main">
        {screen === 'select' ? (
          <RaceSelect onSelectRace={handleSelectRace} />
        ) : loading ? (
          <div className="loading-spinner">
            <div className="spinner" />
            <p>Loading {selectedYear} Round {selectedRound}…</p>
            <p className="loading-time">{loadingTime}s</p>
          </div>
        ) : error ? (
          <div className="error-message">
            <h2>❌ Failed</h2>
            <p>{error}</p>
            <button onClick={() => loadRaceData(selectedYear, selectedRound)}>Retry</button>
            <button onClick={handleGoHome} style={{ marginTop: 8, background: 'transparent', border: '1px solid #aaa', color: '#aaa' }}>
              ← Back to schedule
            </button>
          </div>
        ) : trackData && frames.length > 0 ? (
          <>
            <Navbar onHome={handleGoHome} />
            <RaceViewer
              trackData={trackData}
              frames={frames}
              driverColors={driverColors}
              driverTeams={driverTeams}
              eventName={eventName}
              circuitName={circuitName}
              country={country}
              year={selectedYear}
              hasPrevRace={currentRaceIdx > 0}
              hasNextRace={currentRaceIdx >= 0 && currentRaceIdx < allRaces.length - 1}
              onPrevRace={handlePrevRace}
              onNextRace={handleNextRace}
            />
          </>
        ) : null}
      </main>
    </div>
  );
}

export default App;
