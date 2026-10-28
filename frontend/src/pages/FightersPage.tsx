import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import { getFighters } from '../api';
import type { FighterDivision } from '../types';

const pageVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: [0.25, 1, 0.5, 1] } },
};

const listVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.015 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 3 },
  show: { opacity: 1, y: 0, transition: { duration: 0.15 } },
};

function DivisionList({ division, onSelect }: {
  division: FighterDivision;
  onSelect: (id: number) => void;
}) {
  return (
    <section className="fighters-division">
      <div className="page-header">
        <h2 className="page-title">{division.name}</h2>
        <span className="page-meta">Top {division.fighters.length}</span>
      </div>
      {division.fighters.length === 0 ? (
        <div className="status-msg">No active fighters found.</div>
      ) : (
        <motion.div
          className="fighters-container"
          variants={listVariants}
          initial="hidden"
          animate="show"
        >
          {division.fighters.map((fighter) => (
            <motion.div
              key={fighter.id}
              id={`fighter-${fighter.id}`}
              className="fighter-item"
              variants={itemVariants}
              onClick={() => onSelect(fighter.id)}
              onKeyDown={(event) => event.key === 'Enter' && onSelect(fighter.id)}
              tabIndex={0}
              role="button"
              aria-label={`View ${fighter.name}`}
            >
              <span className="fighter-item-name">{fighter.name}</span>
              <span className="fighter-item-wc">{division.name}</span>
              <span className={`fighter-item-elo ${fighter.model_score >= 60 ? 'high' : ''}`}>
                {Math.round(fighter.model_score)}%
              </span>
            </motion.div>
          ))}
        </motion.div>
      )}
    </section>
  );
}

export default function FightersPage() {
  const [divisions, setDivisions] = useState<FighterDivision[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getFighters()
      .then((data) => {
        setDivisions(data.divisions);
        setTotal(data.total);
      })
      .catch(() => setError('Failed to load fighters.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <motion.main
      className="page-container"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div className="page-header">
        <h1 className="page-title">Top UFC Fighters</h1>
        <span className="page-meta">{total} fighters</span>
      </div>

      {loading && <div className="status-msg">Loading fighters…</div>}
      {error && <div className="status-msg" style={{ color: 'var(--ink-2)' }}>{error}</div>}
      {!loading && !error && divisions.map((division) => (
        <DivisionList key={division.name} division={division} onSelect={(id) => navigate(`/fighters/${id}`)} />
      ))}
    </motion.main>
  );
}
