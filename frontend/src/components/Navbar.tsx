import { Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';

export default function Navbar() {
  const location = useLocation();
  const isFighters = location.pathname.startsWith('/fighters');
  const activeTab = isFighters ? 'fighters' : 'predictions';

  return (
    <header className="nav-header">
      <div className="nav-inner">
        <Link to="/" className="nav-logo" id="nav-logo">
          FightEV
        </Link>
        <nav className="nav-tabs">
          <Link
            to="/"
            className={`nav-tab ${activeTab === 'predictions' ? 'active' : ''}`}
            id="nav-predictions"
          >
            {activeTab === 'predictions' && (
              <motion.div
                layoutId="navPill"
                className="nav-tab-pill"
                transition={{ type: 'spring', stiffness: 450, damping: 35 }}
              />
            )}
            Predictions
          </Link>
          <Link
            to="/fighters"
            className={`nav-tab ${activeTab === 'fighters' ? 'active' : ''}`}
            id="nav-fighters"
          >
            {activeTab === 'fighters' && (
              <motion.div
                layoutId="navPill"
                className="nav-tab-pill"
                transition={{ type: 'spring', stiffness: 450, damping: 35 }}
              />
            )}
            Fighters
          </Link>
        </nav>
      </div>
    </header>
  );
}
