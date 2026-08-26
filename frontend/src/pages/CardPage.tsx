import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { getFights, getFighterByName } from '../api';
import type { FightOut, FighterDetail } from '../types';

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
      staggerChildren: 0.02,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 5 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2 } },
};

export default function CardPage() {
  const [fights, setFights] = useState<FightOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [modalFighter, setModalFighter] = useState<FighterDetail | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [activeFighterName, setActiveFighterName] = useState<string | null>(null);

  useEffect(() => {
    getFights()
      .then(setFights)
      .catch(() => setError('Failed to load upcoming fights.'))
      .finally(() => setLoading(false));
  }, []);

  const prefetchFighter = (name: string) => {
    getFighterByName(name).catch(() => {});
  };

  const openFighterModal = async (name: string) => {
    setActiveFighterName(name);
    setModalLoading(true);
    setModalError(null);
    setModalFighter(null);

    try {
      const data = await getFighterByName(name);
      setModalFighter(data);
    } catch {
      setModalError(`No fighter history found in database for "${name}".`);
    } finally {
      setModalLoading(false);
    }
  };

  const closeModal = () => {
    setActiveFighterName(null);
    setModalFighter(null);
    setModalError(null);
  };

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeModal();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <motion.main
      className="page-container"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div className="page-header centered">
        <h1 className="page-title">UFC Predictions</h1>
      </div>

      {loading && <div className="status-msg">Loading predictions…</div>}
      {error && <div className="status-msg" style={{ color: 'var(--ink-2)' }}>{error}</div>}

      {!loading && fights && fights.length === 0 && (
        <div className="status-msg">No upcoming fights found.</div>
      )}

      {!loading && fights && fights.length > 0 && (
        <motion.div
          className="matchups-list"
          variants={listVariants}
          initial="hidden"
          animate="show"
        >
          {fights.map((fight, i) => {
            const isF1Positive = fight.ev1 > 0;
            const isF2Positive = fight.ev2 > 0;

            return (
              <motion.div
                key={i}
                id={`fight-${i}`}
                className="matchup-row"
                variants={itemVariants}
              >
                {/* Fighter 1 Card */}
                <div
                  className={`fighter-card ${isF1Positive ? 'is-positive' : ''}`}
                  onClick={() => openFighterModal(fight.fighter1)}
                  onMouseEnter={() => prefetchFighter(fight.fighter1)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && openFighterModal(fight.fighter1)}
                  title={`Click to view ${fight.fighter1}'s last 5 fights`}
                >
                  <div className="card-top">
                    <span className="card-name">{fight.fighter1}</span>
                    {fight.predWinner === 1 && (
                      <span className="winner-badge">Predicted Winner</span>
                    )}
                  </div>
                  <div className="card-odds">
                    {fight.odds1 > 0 ? `+${fight.odds1}` : fight.odds1}
                  </div>
                  <div className="card-bottom">
                    <span className="card-elo">
                      Elo: {(fight.eloProb1 * 100).toFixed(1)}%
                    </span>
                    <span className={`card-ev ${isF1Positive ? 'pos' : 'neg'}`}>
                      EV: {fight.ev1 > 0 ? '+' : ''}{(fight.ev1 * 100).toFixed(1)}%
                      {isF1Positive && (fight.kelly1 ?? 0) > 0 && (
                        <span className="card-kelly-badge" title="Suggested Quarter-Kelly bet size">
                          {fight.kelly1}u
                        </span>
                      )}
                    </span>
                  </div>
                </div>

                {/* VS Badge */}
                <div className="vs-circle">vs</div>

                {/* Fighter 2 Card */}
                <div
                  className={`fighter-card ${isF2Positive ? 'is-positive' : ''}`}
                  onClick={() => openFighterModal(fight.fighter2)}
                  onMouseEnter={() => prefetchFighter(fight.fighter2)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && openFighterModal(fight.fighter2)}
                  title={`Click to view ${fight.fighter2}'s last 5 fights`}
                >
                  <div className="card-top">
                    <span className="card-name">{fight.fighter2}</span>
                    {fight.predWinner === 2 && (
                      <span className="winner-badge">Predicted Winner</span>
                    )}
                  </div>
                  <div className="card-odds">
                    {fight.odds2 > 0 ? `+${fight.odds2}` : fight.odds2}
                  </div>
                  <div className="card-bottom">
                    <span className="card-elo">
                      Elo: {(fight.eloProb2 * 100).toFixed(1)}%
                    </span>
                    <span className={`card-ev ${isF2Positive ? 'pos' : 'neg'}`}>
                      EV: {fight.ev2 > 0 ? '+' : ''}{(fight.ev2 * 100).toFixed(1)}%
                      {isF2Positive && (fight.kelly2 ?? 0) > 0 && (
                        <span className="card-kelly-badge" title="Suggested Quarter-Kelly bet size">
                          {fight.kelly2}u
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}

      {/* Fighter History Popup Modal */}
      <AnimatePresence>
        {activeFighterName && (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeModal}
          >
            <motion.div
              className="modal-dialog"
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-header">
                <div className="modal-title-wrap">
                  <div className="modal-title">
                    <span>{modalFighter?.name || activeFighterName}</span>
                    {modalFighter && (
                      <span className="modal-record">
                        {modalFighter.wins}–{modalFighter.losses}{modalFighter.draws > 0 ? `–${modalFighter.draws}` : ''}
                      </span>
                    )}
                  </div>
                </div>
                <button className="modal-close-btn" onClick={closeModal} aria-label="Close modal">
                  ✕
                </button>
              </div>

              <div className="modal-body">
                {modalLoading && <div className="status-msg">Loading fight history…</div>}
                {modalError && <div className="status-msg" style={{ color: 'var(--ink-2)' }}>{modalError}</div>}

                {!modalLoading && modalFighter && (
                  <>
                    <div className="modal-sec-title">Recent Fights (Last 5)</div>
                    {modalFighter.fight_history.length === 0 ? (
                      <div className="status-msg">No previous UFC fights recorded.</div>
                    ) : (
                      <div className="modal-history-list">
                        {modalFighter.fight_history
                          .slice()
                          .reverse()
                          .slice(0, 5)
                          .map((fight, idx) => {
                            const isWin = fight.result === 'win';
                            const isLoss = fight.result === 'loss';
                            return (
                              <div key={`${fight.id}-${idx}`} className="modal-history-row">
                                <span className={`history-tag ${isWin ? 'w' : isLoss ? 'l' : 'other'}`}>
                                  {isWin ? 'W' : isLoss ? 'L' : fight.result.slice(0, 2).toUpperCase()}
                                </span>
                                <div>
                                  <div className="history-opponent">{fight.opponent_name}</div>
                                  <div className="history-event">{fight.event}</div>
                                </div>
                                <span className="history-method">{fight.method}</span>
                                <span className="history-round">
                                  R{fight.round} · {fight.time}
                                </span>
                              </div>
                            );
                          })}
                      </div>
                    )}

                    <div className="modal-footer">
                      <Link
                        to={`/fighters/${modalFighter.id}`}
                        className="modal-link-btn"
                        onClick={closeModal}
                      >
                        View Full Profile →
                      </Link>
                    </div>
                  </>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.main>
  );
}
