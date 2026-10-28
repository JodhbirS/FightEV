import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import { getFighters } from '../api';
import type { FighterListItem } from '../types';

const pageVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: [0.25, 1, 0.5, 1] } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 3 },
  show: { opacity: 1, y: 0, transition: { duration: 0.15 } },
};

export default function FightersPage() {
  const [fighters, setFighters] = useState<FighterListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    getFighters(20, 0, search)
      .then((data) => {
        setFighters(data.fighters);
        setTotal(data.total);
      })
      .catch(() => setError('Failed to load fighters.'))
      .finally(() => setLoading(false));
  }, [search]);

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setSearch(searchInput.trim());
  };

  return (
    <motion.main className="page-container" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="page-header">
        <h1 className="page-title">Fighters</h1>
        <span className="page-meta">{total} {search ? 'matches' : 'featured fighters'}</span>
      </div>

      <form onSubmit={submitSearch} className="search-box">
        <svg className="search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="6.5" cy="6.5" r="4.5" />
          <path d="M10 10L14 14" />
        </svg>
        <input
          id="fighter-search"
          type="text"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Search fighters by name…"
          className="search-input"
        />
      </form>

      {loading && <div className="status-msg">Loading fighters…</div>}
      {error && <div className="status-msg" style={{ color: 'var(--ink-2)' }}>{error}</div>}
      {!loading && !error && fighters.length === 0 && <div className="status-msg">No active fighters found.</div>}
      {!loading && !error && fighters.length > 0 && (
        <motion.div className="fighters-container" initial="hidden" animate="show">
          {fighters.map((fighter) => (
            <motion.div
              key={fighter.id}
              id={`fighter-${fighter.id}`}
              className="fighter-item"
              variants={itemVariants}
              onClick={() => navigate(`/fighters/${fighter.id}`)}
              onKeyDown={(event) => event.key === 'Enter' && navigate(`/fighters/${fighter.id}`)}
              tabIndex={0}
              role="button"
              aria-label={`View ${fighter.name}`}
            >
              <span className="fighter-item-name">{fighter.name}</span>
              <span className="fighter-item-wc">{fighter.weight_class || '—'}</span>
              <span className="fighter-item-profile">View profile</span>
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.main>
  );
}
