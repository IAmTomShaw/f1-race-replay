import './index.css';

interface NavbarProps {
  onHome: () => void;
}

export default function Navbar({ onHome }: NavbarProps) {
  const handleHomeClick = () => {
    onHome();
  };

  return (
    <nav className="navbar">
      <button className="nav-btn nav-home" onClick={handleHomeClick}>
        <svg 
          width="20" 
          height="20" 
          viewBox="0 0 24 24" 
          fill="currentColor"
        >
          <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
        </svg>
        <span>Home</span>
      </button>
    </nav>
  );
}
