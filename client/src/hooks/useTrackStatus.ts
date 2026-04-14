import { useState, useRef, useMemo, useEffect } from 'react';
import { buildRaceEvent } from '../components/Dashboard/RaceEventPopup';
import type { RaceEvent } from '../components/Dashboard/RaceEventPopup';
import type { Frame, TrackStatus } from '../types/api.types';

/**
 * Derives the active track status from the current display frame and fires a
 * `RaceEvent` notification whenever the status changes. Designed to work in
 * tandem with `RaceEventPopup`, which consumes `activeEvent` and `activeStatus`.
 *
 * Status is determined by scanning the sorted status intervals for the latest
 * interval whose `start_time` is at or before the current frame timestamp.
 * Status `'1'` (track clear) is used as the default when no interval applies.
 *
 * A monotonically incrementing counter is used as the event `id` so that the
 * same status code can re-trigger the popup animation if it recurs later in
 * the race (e.g. a second safety car period).
 *
 * @param {Frame | null} displayFrame - The frame currently being rendered;
 *   status derivation is skipped when null.
 * @param {TrackStatus[]} trackStatuses - Unordered array of track status intervals
 *   for the session; sorted internally by `start_time`.
 *
 * @returns {{
 *   activeEvent: RaceEvent | null,
 *   activeStatus: string,
 *   resetStatus: () => void,
 * }}
 */
export function useTrackStatus(displayFrame: Frame | null, trackStatuses: TrackStatus[]) {
  const [activeEvent, setActiveEvent]   = useState<RaceEvent | null>(null);
  const [activeStatus, setActiveStatus] = useState<string>('1');
  const eventCounterRef = useRef<number>(0);
  const lastStatusRef   = useRef<string>('1');

  const sortedStatuses = useMemo(
    () => [...trackStatuses].sort((a, b) => a.start_time - b.start_time),
    [trackStatuses]
  );

  /**
   * On each frame advance, scans `sortedStatuses` to find the latest interval
   * whose `start_time` is at or before the current frame timestamp `t`. When
   * the derived status differs from the last recorded status, updates both
   * reactive state values and constructs a new `RaceEvent` for the popup.
   *
   * The early-break optimisation relies on `sortedStatuses` being in ascending
   * order: once a status with `start_time > t` is encountered, no later entries
   * can apply and the loop exits.
   */
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

  /**
   * Resets the last-seen status back to `'1'` (track clear) without clearing
   * `activeEvent`. Should be called on playback restart so the next status
   * change is detected as a genuine transition rather than being suppressed
   * by a stale `lastStatusRef` value from the previous playthrough.
   */
  const resetStatus = () => {
    lastStatusRef.current = '1';
    setActiveStatus('1');
  };

  return { activeEvent, activeStatus, resetStatus };
}
