import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.tsx';
import './index.css';

/**
 * Titillium Web is the primary typeface used throughout the application.
 * Four weights are imported to cover the full typographic scale defined in
 * `variables.css`: regular (400), semi-bold (600), bold (700), and black (900).
 */
import '@fontsource/titillium-web';
import '@fontsource/titillium-web/600.css';
import '@fontsource/titillium-web/700.css';
import '@fontsource/titillium-web/900.css';

/**
 * Application entry point. Mounts the React component tree into the `#root`
 * element defined in `index.html`.
 */
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);