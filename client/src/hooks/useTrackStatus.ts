import { useState, useRef, useMemo, useEffect } from 'react';
import { buildRaceEvent } from '../components/Dashboard/RaceEventPopup';
import type { RaceEvent } from '../components/Dashboard/RaceEventPopup';
import type { Frame, TrackStatus } from '../types/api.types';

export function useTrackStatus(displayFrame: Frame | null, trackStatuses: TrackStatus[]) {
  const [activeEvent, setActiveEvent]   = useState<RaceEvent | null>(null);
  const [activeStatus, setActiveStatus] = useState<string>('1');

  const eventCounterRef = useRef<number>(0);
  const lastStatusRef   = useRef<string>('1');

  const sortedStatuses = useMemo(
    () => [...trackStatuses].sort((a, b) => a.start_time - b.start_time),
    [trackStatuses]
  );

  useEffect(() => {
    if (!displayFrame || sortedStatuses.length === 0) return;
    const t = displayFrame.t;

    let status = '1';
    for (const s of sortedStatuses) {
      if (s.start_time <= t) status = s.status;
      else break;
    }

    if (status !== lastStatusRef.current) {
      lastStatusRef.current = status;
      setActiveStatus(status);
      const event = buildRaceEvent(status, ++eventCounterRef.current);
      if (event) setActiveEvent(event);
    }
  }, [displayFrame, sortedStatuses]);

  // Called on restart so the next status change re-fires correctly
  const resetStatus = () => {
    lastStatusRef.current = '1';
    setActiveStatus('1');
  };

  return { activeEvent, activeStatus, resetStatus };
}
