import { flagUrl } from "../../../lib/assets";
import type { WeatherData } from '../../../types/api.types';
import '../Weather/index.css';
import './index.css';

interface SessionBannerProps {
  eventName?: string;
  circuitName?: string;
  country?: string;
  year?: number;
  weather?: WeatherData | null;
}

const WEATHER_ITEMS: {
  label: string;
  icon: React.ReactNode;
  value: (w: WeatherData) => string | null;
}[] = [
  {
    label: 'AIR',
    icon: <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a5 5 0 0 0-5 5v7.55A7 7 0 1 0 19 14V7a5 5 0 0 0-5-5zm0 2a3 3 0 0 1 3 3v1h-6V7a3 3 0 0 1 3-3z"/></svg>,
    value: w => w.air_temp   != null ? `${Math.round(w.air_temp)}°C`    : null,
  },
  {
    label: 'TRK',
    icon: <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 0 0 8 20c4 0 4-2 8-2s4 2 8 2v-2c-4 0-4-2-8-2-1.13 0-1.9.16-2.53.33C14.54 12.4 16 9.7 17 8z"/></svg>,
    value: w => w.track_temp != null ? `${Math.round(w.track_temp)}°C`  : null,
  },
  {
    label: 'HUM',
    icon: <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2C20 10.48 17.33 6.55 12 2z"/></svg>,
    value: w => w.humidity   != null ? `${Math.round(w.humidity)}%`     : null,
  },
  {
    label: 'WND',
    icon: <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M14.5 6.5C14.5 5.12 13.38 4 12 4c-1.38 0-2.5 1.12-2.5 2.5 0 1.07.67 1.98 1.62 2.34L3 9v1h13.5c1.1 0 2-.9 2-2s-.9-2-2-2h-1.18c.1-.31.18-.65.18-1zM3 14h10.5c1.1 0 2 .9 2 2s-.9 2-2 2H12v1h1.5c1.66 0 3-1.34 3-3s-1.34-3-3-3H3v1zm16-3H3v1h16c.55 0 1 .45 1 1s-.45 1-1 1h-1v1h1c1.1 0 2-.9 2-2s-.9-2-2-2z"/></svg>,
    value: w => w.wind_speed != null ? `${Math.round(w.wind_speed)}km/h`: null,
  },
];

export default function SessionBanner({ eventName, circuitName, country, year, weather }: SessionBannerProps) {
  return (
    <div className="session-banner">
      <div className="event-info-container">
        <div className="event-section-left">
          <div className="grand-prix-name">{year} {eventName || 'GRAND PRIX'}</div>
        </div>

        <div className="event-section-right">
          {country && (
            <img
              src={flagUrl(`Flag_of_${country.replace(/\s/g, '_')}.png`)}
              alt={`${country} flag`}
              className="country-flag"
              onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
            />
          )}
          {circuitName && (
            <div className="location-info">
              <div className="circuit-name">{circuitName}</div>
            </div>
          )}

          {weather && (
            <div className={`weather-strip ${weather.rain_state === 'RAINING' ? 'weather-strip--wet' : ''}`}>
              <div className="weather-strip-status">
                {weather.rain_state === 'RAINING' ? (
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M17.66 8L12 2.35 6.34 8C4.78 9.56 4 11.64 4 13.64s.78 4.11 2.34 5.67 3.61 2.35 5.66 2.35 4.1-.79 5.66-2.35S20 15.64 20 13.64 19.22 9.56 17.66 8z"/>
                  </svg>
                ) : (
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M6.76 4.84l-1.8-1.79-1.41 1.41 1.79 1.79 1.42-1.41zM4 10.5H1v2h3v-2zm9-9.95h-2V3.5h2V.55zm7.45 3.91l-1.41-1.41-1.79 1.79 1.41 1.41 1.79-1.79zm-3.21 13.7l1.79 1.8 1.41-1.41-1.8-1.79-1.4 1.4zM20 10.5v2h3v-2h-3zm-8-5c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm-1 16.95h2V19.5h-2v2.95zm-7.45-3.91l1.41 1.41 1.79-1.8-1.41-1.41-1.79 1.8z"/>
                  </svg>
                )}
                <span>{weather.rain_state === 'RAINING' ? 'WET' : 'DRY'}</span>
              </div>

              <div className="weather-strip-divider" />

              {WEATHER_ITEMS.map(({ label, icon, value }) => {
                const val = value(weather);
                if (!val) return null;
                return (
                  <div key={label} className="weather-strip-item">
                    <div className="weather-strip-icon-label">
                      <span className="weather-strip-icon">{icon}</span>
                      <span className="weather-strip-label">{label}</span>
                    </div>
                    <span className="weather-strip-value">{val}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
