import { useState, useEffect } from 'react';
import { telemetryService } from '../../../services/telemetryService';
import './index.css';

interface CircuitResult {
  year: number;
  round: number;
  event_name: string;
  position: number | null;
  is_retired: boolean;
  team: string;
}

interface DriverSummaryPanelProps {
  circuitName: string;
  driverCodes: string[];
  driverColors: Record<string, [number, number, number]>;
  driverTeams: Record<string, string>;
  selectedDriver: string;
  onDriverSelect: (code: string) => void;
  onClose: () => void;
}

export default function DriverSummaryPanel({
  circuitName, driverCodes, driverColors, driverTeams,
  selectedDriver, onDriverSelect, onClose,
}: DriverSummaryPanelProps) {
  const [results, setResults]   = useState<CircuitResult[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const sortedDrivers = [...driverCodes].sort();

  useEffect(() => {
    if (!selectedDriver) return;
    setLoading(true);
    setError(null);
    setResults([]);

    telemetryService.getDriverCircuitHistory(selectedDriver, circuitName)
      .then(setResults)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedDriver, circuitName]);

  const color = selectedDriver && driverColors[selectedDriver]
    ? `rgb(${driverColors[selectedDriver].join(',')})`
    : 'var(--color-red)';

  
  const bestResult = results.length > 0
      ? Math.min(...results
          .filter(r => r.position !== null && !r.is_retired)
          .map(r => r.position!))
      : null;

  return (
    <div className="driver-summary">
      <div className="dc-header">
        <span className="dc-title">Driver Summary</span>
        <button className="dc-close" onClick={onClose} title="Exit summary">✕</button>
      </div>

      <div className="dc-select-wrapper">
        <select
          className="dc-select"
          value={selectedDriver}
          onChange={e => onDriverSelect(e.target.value)}
        >
          <option value="">Select a driver</option>
          {sortedDrivers.map(code => (
            <option key={code} value={code}>{code}</option>
          ))}
        </select>
        {selectedDriver && (
          <div className="dc-select-accent" style={{ backgroundColor: color }} />
        )}
      </div>

      {loading && (
        <div className="dc-loading">
          <div className="dc-spinner" />
          <span>Loading history…</span>
        </div>
      )}

      {error && <div className="dc-error">{error}</div>}

      {!loading && !error && selectedDriver && results.length === 0 && (
        <div className="dc-empty">No data found for {selectedDriver} at this circuit.</div>
      )}

      {results.length > 0 && (
        <>
          <div className="dc-summary">
            <div className="dc-summary-item">
              <span className="dc-summary-label">RACES</span>
              <span className="dc-summary-value">{results.length}</span>
            </div>
            <div className="dc-summary-item">
              <span className="dc-summary-label">BEST</span>
              <span className="dc-summary-value">
                {bestResult !== null ? `P${bestResult}` : '—'}
                </span>
            </div>
            <div className="dc-summary-item">
              <span className="dc-summary-label">WINS</span>
              <span className="dc-summary-value">
                {results.filter(r => r.position === 1 && !r.is_retired).length}
              </span>
            </div>
            <div className="dc-summary-item">
              <span className="dc-summary-label">DNF</span>
              <span className="dc-summary-value">
                {results.filter(r => r.is_retired).length}
              </span>
            </div>
          </div>

          <div className="dc-results">
            {results.map(r => (
              <div key={`${r.year}-${r.round}`} className={`dc-row ${r.is_retired ? 'dc-row--dnf' : ''} ${r.position === 1 ? 'dc-row--win' : ''}`}>
                <span className="dc-row-year">{r.year}</span>
                <span className="dc-row-team">{r.team || '—'}</span>
                <span className="dc-row-pos">
                  {r.is_retired
                    ? <span className="dc-dnf">DNF</span>
                    : r.position
                      ? <span className="dc-dnf">P{r.position}</span>
                      : '—'
                  }
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
