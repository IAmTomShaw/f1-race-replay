import f1logo from '../../../../assets/f1-logo.png';
import './index.css';

/**
 * F1Header renders the top-of-panel Formula 1 branding logo.
 *
 * @returns {JSX.Element} A header bar containing the F1 logo image.
 */
export default function F1Header() {
  return (
    <div className="f1-header">
      <div className="f1-logo">
        <img src={f1logo} alt="F1 Logo" className="f1-logo-img" />
      </div>
    </div>
  );
}