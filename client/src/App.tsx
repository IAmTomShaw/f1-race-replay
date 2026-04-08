import { useState } from 'react';
import RaceViewer from './components/Dashboard/RaceViewer';
import RaceSelect from './components/RaceSelect';
import { useRaceLoader } from './hooks/useRaceLoader';
import './styles/variables.css';
import './App.css';

type Screen = 'select' | 'viewer';

function App() {
  const [screen, setScreen] = useState<Screen>('select');

  const {
    selectedYear, selectedRound,
    eventName, circuitName, country, totalLaps,
    trackData, frames, driverColors, driverTeams, officialPositions, trackStatuses,
    loading, error,
    hasPrevRace, hasNextRace,
    selectRace, goToPrevRace, goToNextRace, loadRaceData, reset,
  } = useRaceLoader();

  const handleSelectRace = (year: number, round: number) => {
    selectRace(year, round);
    setScreen('viewer');
  };

  const handleGoHome = () => {
    reset();
    setScreen('select');
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
          <RaceViewer
            trackData={trackData}
            frames={frames}
            driverColors={driverColors}
            driverTeams={driverTeams}
            eventName={eventName}
            circuitName={circuitName}
            country={country}
            year={selectedYear}
            totalLaps={totalLaps}
            officialPositions={officialPositions}
            trackStatuses={trackStatuses}
            hasPrevRace={hasPrevRace}
            hasNextRace={hasNextRace}
            onHome={handleGoHome}
            onPrevRace={goToPrevRace}
            onNextRace={goToNextRace}
          />
        ) : null}
      </main>
    </div>
  );
}

export default App;
