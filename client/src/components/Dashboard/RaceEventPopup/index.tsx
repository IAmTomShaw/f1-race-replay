import './index.css';

export interface RaceEvent {
  status: string;
  label: string;
  color: string;
  icon: React.ReactNode;
  id: number; // unique per trigger so same status can re-fire
}

const STATUS_CONFIG: Record<string, Omit<RaceEvent, 'id' | 'status'>> = {
  '2': {
    label: 'Yellow Flag',
    color: '#FFD700',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4 22V4l1-.5C6.5 3 8.5 2 11 2c2 0 3.5.5 5 1s3 1 4 1l1 .2V14.5l-1 .3c-1 .3-2.5.7-4 .7-1.8 0-3.3-.5-4.8-1C5.5 14.5 5 14 5 14v8H4z"/>
      </svg>
    ),
  },
  '4': {
    label: 'Safety Car',
    color: '#F97316',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.85 7h10.29l1.08 3.11H5.77L6.85 7zM19 17H5v-5h14v5z"/>
        <circle cx="7.5" cy="14.5" r="1.5"/>
        <circle cx="16.5" cy="14.5" r="1.5"/>
      </svg>
    ),
  },
  '5': {
    label: 'Red Flag',
    color: '#EF4444',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4 22V4l1-.5C6.5 3 8.5 2 11 2c2 0 3.5.5 5 1s3 1 4 1l1 .2V14.5l-1 .3c-1 .3-2.5.7-4 .7-1.8 0-3.3-.5-4.8-1C5.5 14.5 5 14 5 14v8H4z"/>
      </svg>
    ),
  },
  '6': {
    label: 'Virtual Safety Car',
    color: '#FB923C',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.85 7h10.29l1.08 3.11H5.77L6.85 7zM19 17H5v-5h14v5z"/>
        <circle cx="7.5" cy="14.5" r="1.5"/>
        <circle cx="16.5" cy="14.5" r="1.5"/>
      </svg>
    ),
  },
  '7': {
    label: 'VSC Ending',
    color: '#FDE68A',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.85 7h10.29l1.08 3.11H5.77L6.85 7zM19 17H5v-5h14v5z"/>
        <circle cx="7.5" cy="14.5" r="1.5"/>
        <circle cx="16.5" cy="14.5" r="1.5"/>
      </svg>
    ),
  },
};

const DISMISS_MS = 4000;

interface RaceEventPopupProps {
  event: RaceEvent | null;
  isActive: boolean;
}

export function buildRaceEvent(status: string, id: number): RaceEvent | null {
  const config = STATUS_CONFIG[status];
  if (!config) return null;
  return { ...config, status, id };
}

export default function RaceEventPopup({ event, isActive }: RaceEventPopupProps) {
  if (!event) return null;

  return (
    <div className={`race-event-popup ${isActive ? 'race-event-popup--visible' : ''}`}>
      <div className="race-event-popup-bar" style={{ backgroundColor: event.color }} />
      <span className="race-event-popup-icon" style={{ color: event.color }}>
        {event.icon}
      </span>
      <span className="race-event-popup-label">{event.label}</span>
    </div>
  );
}
