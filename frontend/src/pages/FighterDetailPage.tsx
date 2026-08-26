import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { getFighter } from '../api';
import type { FighterDetail } from '../types';

const pageVariants: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.25, 1, 0.5, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: [0.25, 1, 0.5, 1] } },
};

interface TooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: {
      fight_sequence: number;
      elo_after: number;
      opponent_name: string;
      result: string;
      event: string;
    };
  }>;
}

function ChartTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const isWin = d.result === 'win';
  const isLoss = d.result === 'loss';

  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid var(--line)',
      borderRadius: 8,
      padding: '8px 12px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
      fontSize: '0.75rem',
    }}>
      <div style={{ color: 'var(--ink-3)', fontSize: '0.625rem', marginBottom: 2 }}>{d.event}</div>
      <div style={{ fontWeight: 600, marginBottom: 3 }}>vs {d.opponent_name}</div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span className={`history-tag ${isWin ? 'w' : isLoss ? 'l' : 'other'}`} style={{ padding: '1px 6px' }}>
          {d.result.toUpperCase().slice(0, 1)}
        </span>
        <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--blue)' }}>
          {Math.round(d.elo_after)} Elo
        </span>
      </div>
    </div>
  );
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

  const chartData = fighter.elo_history.map((p) => ({
    fight_sequence: p.fight_sequence,
    elo_after: p.elo_after,
    opponent_name: p.opponent_name,
    result: p.result,
    event: p.event,
  }));

  const eloMin = Math.min(...chartData.map((d) => d.elo_after));
  const eloMax = Math.max(...chartData.map((d) => d.elo_after));
  const yMin = Math.floor((eloMin - 30) / 50) * 50;
  const yMax = Math.ceil((eloMax + 30) / 50) * 50;

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
            <span className="stat-val" style={{ color: fighter.current_elo > 0 ? 'var(--blue)' : 'var(--ink-3)', fontSize: fighter.current_elo > 0 ? '1.125rem' : '0.85rem', fontWeight: 600 }}>
              {fighter.current_elo > 0 ? Math.round(fighter.current_elo) : 'Inactive'}
            </span>
            <span className="stat-label">{fighter.current_elo > 0 ? 'Elo Rating' : 'Status'}</span>
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
      {chartData.length > 1 && (
        <section style={{ marginBottom: 16 }}>
          <div className="section-label">
            Elo History <span>{chartData.length} fights</span>
          </div>
          <div className="chart-panel">
            <ResponsiveContainer width="100%" height={210}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line-subtle)" vertical={false} />
                <XAxis
                  dataKey="fight_sequence"
                  tick={{ fontSize: 10, fill: 'var(--ink-3)', fontFamily: 'var(--ff)' }}
                  axisLine={{ stroke: 'var(--line)' }}
                  tickLine={false}
                />
                <YAxis
                  domain={[yMin, yMax]}
                  tick={{ fontSize: 10, fill: 'var(--ink-3)', fontFamily: 'var(--ff)' }}
                  axisLine={false}
                  tickLine={false}
                  width={38}
                />
                <ReferenceLine y={1000} stroke="var(--line)" strokeDasharray="4 3" />
                <Tooltip content={<ChartTooltip />} />
                <Line
                  type="monotone"
                  dataKey="elo_after"
                  stroke="var(--blue)"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: 'var(--blue)', stroke: '#FFFFFF', strokeWidth: 1.5 }}
                  activeDot={{ r: 4, fill: 'var(--blue)', stroke: '#FFFFFF', strokeWidth: 2 }}
                  isAnimationActive
                  animationDuration={600}
                  animationEasing="ease-out"
                />
              </LineChart>
            </ResponsiveContainer>
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
