import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import { getFighters } from '../api';
import type { FighterListItem } from '../types';

const PAGE_SIZE = 25;

const pageVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: [0.25, 1, 0.5, 1] } },
};

const listVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.015,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 3 },
  show: { opacity: 1, y: 0, transition: { duration: 0.15 } },
};

export default function FightersPage() {
  const [fighters, setFighters] = useState<FighterListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const navigate = useNavigate();

  const fetchData = useCallback(async (off: number, q: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getFighters(PAGE_SIZE, off, q);
      setFighters(data.fighters);
      setTotal(data.total);
    } catch {
      setError('Failed to load fighters.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(offset, search);
  }, [offset, search, fetchData]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setSearch(searchInput);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <motion.main
      className="page-container"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div className="page-header">
        <h1 className="page-title">Fighters</h1>
        <span className="page-meta">{total.toLocaleString()} fighters</span>
      </div>

      <form onSubmit={handleSearch} className="search-box">
        <svg
          className="search-icon"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <circle cx="6.5" cy="6.5" r="4.5" />
          <path d="M10 10L14 14" />
        </svg>
        <input
          id="fighter-search"
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search fighters by name…"
          className="search-input"
        />
      </form>

      {loading && <div className="status-msg">Loading fighters…</div>}
      {error && <div className="status-msg" style={{ color: 'var(--ink-2)' }}>{error}</div>}

      {!loading && !error && fighters.length === 0 && (
        <div className="status-msg">No fighters found.</div>
      )}

      {!loading && !error && fighters.length > 0 && (
        <>
          <motion.div
            className="fighters-container"
            variants={listVariants}
            initial="hidden"
            animate="show"
          >
            {fighters.map((f) => (
              <motion.div
                key={f.id}
                id={`fighter-${f.id}`}
                className="fighter-item"
                variants={itemVariants}
                onClick={() => navigate(`/fighters/${f.id}`)}
                onKeyDown={(e) => e.key === 'Enter' && navigate(`/fighters/${f.id}`)}
                tabIndex={0}
                role="button"
                aria-label={`View ${f.name}`}
              >
                <span className="fighter-item-name">{f.name}</span>
                <span className="fighter-item-wc">{f.weight_class || '—'}</span>
                <span className={`fighter-item-elo ${f.current_elo >= 1100 ? 'high' : ''}`}>
                  {Math.round(f.current_elo)}
                </span>
              </motion.div>
            ))}
          </motion.div>

          <div className="pagination-bar">
            <button
              className="page-btn"
              id="prev-btn"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ← Prev
            </button>
            <span className="page-info">
              {currentPage} / {totalPages}
            </span>
            <button
              className="page-btn"
              id="next-btn"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </motion.main>
  );
}
