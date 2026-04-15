import axios from 'axios';

/**
 * Base URL for all API requests. Resolved from the `VITE_API_URL` environment
 * variable at build time, with a local development server as the fallback.
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Pre-configured Axios instance used for all HTTP requests in the application.
 *
 * Configuration:
 * - `baseURL` — resolved from `VITE_API_URL` or defaults to `http://localhost:8000`.
 * - `timeout` — set to 3,000,000 ms (50 minutes) to accommodate large telemetry
 *   payloads that may take significant time to fetch or process server-side.
 * - `Content-Type` — defaults to `application/json` for all requests.
 *
 * Two interceptor pairs are attached (see below) for request/response logging.
 */
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 3000000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor: logs the HTTP method and URL of every outgoing request.
 * On error (e.g. request could not be constructed), logs the error and re-rejects
 * so callers receive the original rejection without it being silently swallowed.
 */
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

/**
 * Response interceptor: logs the HTTP status code and URL of every successful
 * response. On error (non-2xx response or network failure), logs the response
 * body if available, otherwise the JS error message, then re-rejects so the
 * error propagates to the original caller.
 */
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

export default api;