import { useNavigate } from 'react-router-dom';
import RaceSelect from '../components/RaceSelect';

/**
 * RaceSelectPage is the route-level page component for `/` (the root path).
 * It is a thin adapter between React Router and the `RaceSelect` component,
 * converting a race selection into a URL navigation so `RaceSelect` itself
 * remains decoupled from the router.
 *
 * @returns {JSX.Element} The rendered race selection screen.
 */
export default function RaceSelectPage() {
  const navigate = useNavigate();

  /**
   * Navigates to the dashboard for the chosen race.
   * Called by `RaceSelect` when the user confirms their selection.
   *
   * @param {number} year - The season year of the selected race.
   * @param {number} round - The round number of the selected race.
   */
  const handleSelectRace = (year: number, round: number) => {
    navigate(`/f1-race-replay/race/${year}/${round}`);
  };

  return <RaceSelect onSelectRace={handleSelectRace} />;
}
