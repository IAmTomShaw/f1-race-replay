import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useRaceLoader } from '../hooks/useRaceLoader';
import RaceViewer from '../components/Dashboard/RaceViewer';

/**
 * DashboardPage is the route-level page component for `/race/:year/:round`.
 * It bridges the React Router URL params and the `useRaceLoader` hook, then
 * renders the full `RaceViewer` once data is available.
 *
 * Three render states are handled before the viewer is shown:
 * - **Loading** — a spinner while track and frame data are being fetched.
 * - **Error** — an error panel with inline retry and home navigation buttons.
 * - **Empty** — renders nothing (`null`) if the loader finished without data
 *   (e.g. a race exists in the schedule but has no telemetry frames yet).
 *
 * Navigation side-effects (home, prev/next race) are handled here via
 * `useNavigate` so `RaceViewer` remains decoupled from the router.
 *
 * @returns {JSX.Element | null} The loading spinner, error panel, full viewer,
 *   or null depending on the current load state.
 */
export default function DashboardPage() {
  const { year: yearStr, round: roundStr } = useParams<{ year: string; round: string }>();
  const navigate = useNavigate();

  const year  = Number(yearStr);
  const round = Number(roundStr);

  const {
    eventName, circuitName, country, totalLaps,
    trackData, frames, driverColors, driverTeams, officialPositions, trackStatuses,
    loading, error,
    hasPrevRace, hasNextRace,
    prevRace, nextRace,
    selectRace, loadRaceData, reset,
  } = useRaceLoader();

  /**
   * Triggers a full data load whenever the URL params change (i.e. when the
   * user navigates to a different race). `selectRace` is intentionally omitted
   * from the dependency array — it is recreated each render but its behaviour
   * is stable, and including it would cause an infinite fetch loop.
   */
  useEffect(() => {
    if (year && round) selectRace(year, round);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, round]);

  /**
   * Clears all loaded race data and navigates back to the race selection screen.
   * Calling `reset()` before navigating ensures stale data isn't briefly visible
   * if the user returns to the dashboard for a different race.
   */
  const handleGoHome = () => {
    reset();
    navigate('/');
  };

  /** Navigates to the previous race in the cross-season list; no-ops when `prevRace` is null. */
  const handlePrevRace = () => {
    if (prevRace) navigate(`/race/${prevRace.year}/${prevRace.round}`);
  };

  /** Navigates to the next race in the cross-season list; no-ops when `nextRace` is null. */
  const handleNextRace = () => {
    if (nextRace) navigate(`/race/${nextRace.year}/${nextRace.round}`);
  };

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
        <p>Loading {year} Round {round}…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-message">
        <h2>❌ Failed</h2>
        <p>{error}</p>
        <button onClick={() => loadRaceData(year, round)}>Retry</button>
        <button
          onClick={handleGoHome}
          style={{ marginTop: 8, background: 'transparent', border: '1px solid #aaa', color: '#aaa' }}
        >
          ← Back to schedule
        </button>
      </div>
    );
  }

  if (!trackData || frames.length === 0) return null;

  return (
    <RaceViewer
      trackData={trackData}
      frames={frames}
      driverColors={driverColors}
      driverTeams={driverTeams}
      eventName={eventName}
      circuitName={circuitName}
      country={country}
      year={year}
      totalLaps={totalLaps}
      officialPositions={officialPositions}
      trackStatuses={trackStatuses}
      hasPrevRace={hasPrevRace}
      hasNextRace={hasNextRace}
      onHome={handleGoHome}
      onPrevRace={handlePrevRace}
      onNextRace={handleNextRace}
    />
  );
}
