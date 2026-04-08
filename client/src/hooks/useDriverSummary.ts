import { useState, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';

interface CircuitResult {
  year: number;
  round: number;
  event_name: string;
  position: number | null;
  is_retired: boolean;
  team: string;
}

export function useDriverSummary(selectedDriver: string, circuitName: string) {
  const [results, setResults] = useState<CircuitResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    if (!selectedDriver) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    setResults([]);

    telemetryService.getDriverCircuitHistory(selectedDriver, circuitName)
      .then(setResults)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedDriver, circuitName]);

  const bestResult = results.length > 0
    ? Math.min(...results
        .filter(r => r.position !== null && !r.is_retired)
        .map(r => r.position!))
    : null;

  const wins = results.filter(r => r.position === 1 && !r.is_retired).length;
  const dnfs = results.filter(r => r.is_retired).length;

  return { results, loading, error, bestResult, wins, dnfs };
}
