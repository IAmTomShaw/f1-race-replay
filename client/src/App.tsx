import { Routes, Route } from 'react-router-dom';
import RaceSelectPage from './pages/RaceSelectPage';
import DashboardPage from './pages/DashboardPage';
import './styles/variables.css';
import './App.css';

/**
 * App is the root application component. It defines the client-side route
 * structure and renders the appropriate page for each URL:
 *
 * - `/` → `RaceSelectPage` — the race picker where users choose a season and round.
 * - `/race/:year/:round` → `DashboardPage` — the live replay viewer for the selected race.
 *
 * @returns {JSX.Element} The root layout shell with the active route rendered inside.
 */
export default function App() {
  return (
    <div className="app">
      <main className="app-main">
        <Routes>
          <Route path="/" element={<RaceSelectPage />} />
          <Route path="/race/:year/:round" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}