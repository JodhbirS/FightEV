import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import {
  Cell, Pie, PieChart, ResponsiveContainer, Tooltip,
} from 'recharts';
import { getFighter } from '../api';
import type { FighterDetail } from '../types';

const pageVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: [0.25, 1, 0.5, 1] } },
};

interface PieTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: {
      name: string;
      value: number;
    };
  }>;
}

function ChartTooltip({ active, payload }: PieTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;

  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid var(--line)',
      borderRadius: 8,
      padding: '8px 12px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
      fontSize: '0.75rem',
    }}>
      <div style={{ fontWeight: 600 }}>{d.name}</div>
      <div style={{ color: 'var(--ink-2)', marginTop: 2 }}>{d.value} fights</div>
    </div>
  );
}

function methodCategory(method: string) {
  const normalized = method.toLowerCase();
  const type = normalized.includes('ko') || normalized.includes('tko')
    ? 'KO/TKO'
    : normalized.includes('sub')
      ? 'Submission'
      : 'Decision';
  return `Win · ${type}`;
}

export default function FighterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [fighter, setFighter] = useState<FighterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getFighter(Number(id))
      .then(setFighter)
      .catch((err) => setError(err.message || 'Failed to load fighter.'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <motion.main
        className="page-container"
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <div className="status-msg">Loading fighter…</div>
      </motion.main>
    );
  }

  if (error || !fighter) {
    return (
      <motion.main
        className="page-container"
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <Link to="/fighters" className="back-link">
          ← Fighters
        </Link>
        <div className="status-msg" style={{ color: 'var(--ink-2)' }}>
          {error || 'Fighter not found.'}
        </div>
      </motion.main>
    );
  }

  const methodCounts = fighter.method_history.reduce<Record<string, number>>((counts, fight) => {
    if (fight.result === 'win') {
      const category = methodCategory(fight.method);
      counts[category] = (counts[category] || 0) + 1;
    }
    return counts;
  }, {});
  const chartData = Object.entries(methodCounts).map(([name, value]) => ({ name, value }));
  const chartColors = ['var(--pos)', 'var(--blue)', '#78A889'];

  return (
    <motion.main
      className="page-container"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div style={{ paddingTop: 16 }}>
        <Link to="/fighters" className="back-link" id="nav-back">
          ← Fighters
        </Link>
      </div>

      <div className="detail-card-panel">
        <div className="detail-name-row">
          <h1 className="detail-name" id="fighter-name">
            {fighter.name}
          </h1>
          <span className="detail-record">
            {fighter.wins}–{fighter.losses}{fighter.draws > 0 ? `–${fighter.draws}` : ''}
          </span>
          {fighter.weight_class && (
            <span className="detail-badge">{fighter.weight_class}</span>
          )}
        </div>

        {/* Stats summary */}
        <div className="stat-summary">
          <div className="stat-block">
            <span className="stat-val" style={{ color: fighter.is_active ? 'var(--blue)' : 'var(--ink-3)', fontSize: '0.85rem', fontWeight: 600 }}>
              {fighter.is_active ? 'Active' : 'Inactive'}
            </span>
            <span className="stat-label">Status</span>
          </div>
          <div className="stat-block">
            <span className="stat-val">{fighter.total_fights}</span>
            <span className="stat-label">Total Fights</span>
          </div>
          <div className="stat-block">
            <span className="stat-val" style={{ color: 'var(--pos)' }}>{fighter.wins}</span>
            <span className="stat-label">Wins</span>
          </div>
          <div className="stat-block">
            <span className="stat-val">{fighter.losses}</span>
            <span className="stat-label">Losses</span>
          </div>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <section style={{ marginBottom: 16 }}>
          <div className="section-label">
            Victory Methods <span>{fighter.wins} wins</span>
          </div>
          <div className="chart-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '12px 18px' }}>
            <ResponsiveContainer width="55%" height={190}>
              <PieChart>
                <Tooltip content={<ChartTooltip />} />
                <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={78} innerRadius={42} paddingAngle={2}>
                  {chartData.map((entry, index) => (
                    <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9, fontSize: '0.6875rem', color: 'var(--ink-2)' }}>
              {chartData.map((entry, index) => (
                <span key={entry.name} style={{ whiteSpace: 'nowrap' }}>
                  <span style={{ color: chartColors[index % chartColors.length] }}>●</span> {entry.name.replace('Win · ', '')}: {entry.value}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Match history */}
      <section>
        <div className="section-label">
          Fight History <span>{fighter.total_fights} fights</span>
        </div>

        <div className="history-panel">
          {fighter.fight_history.slice().reverse().map((fight, i) => {
            const isWin = fight.result === 'win';
            const isLoss = fight.result === 'loss';
            return (
              <div key={`${fight.id}-${i}`} className="history-item">
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
      </section>
    </motion.main>
  );
}
