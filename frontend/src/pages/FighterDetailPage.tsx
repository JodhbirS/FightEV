import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion, type Variants } from 'framer-motion';
import {
  Bar, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
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
      outcome_score: number;
      finish_rate: number;
      finish: boolean;
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
          {d.finish ? 'Finish' : 'Decision'} · {Math.round(d.finish_rate)}% finish rate
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

  const chartData = fighter.model_history.map((p) => ({
    fight_sequence: p.fight_sequence,
    outcome_score: p.result === 'win' ? 1 : p.result === 'loss' ? -1 : 0,
    finish: p.finish,
    finish_rate: p.finish_rate,
    opponent_name: p.opponent_name,
    result: p.result,
    event: p.event,
  }));

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
      {chartData.length > 1 && (
        <section style={{ marginBottom: 16 }}>
          <div className="section-label">
            Results &amp; Finishes <span>{chartData.length} fights</span>
          </div>
          <div className="chart-panel">
            <ResponsiveContainer width="100%" height={210}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line-subtle)" vertical={false} />
                <XAxis
                  dataKey="fight_sequence"
                  tick={{ fontSize: 10, fill: 'var(--ink-3)', fontFamily: 'var(--ff)' }}
                  axisLine={{ stroke: 'var(--line)' }}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="outcome"
                  domain={[-1.2, 1.2]}
                  ticks={[-1, 0, 1]}
                  tickFormatter={(value) => value === 1 ? 'W' : value === -1 ? 'L' : '—'}
                  tick={{ fontSize: 10, fill: 'var(--ink-3)', fontFamily: 'var(--ff)' }}
                  axisLine={false}
                  tickLine={false}
                  width={38}
                />
                <YAxis
                  yAxisId="finish"
                  orientation="right"
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                  tick={{ fontSize: 10, fill: 'var(--ink-3)', fontFamily: 'var(--ff)' }}
                  axisLine={false}
                  tickLine={false}
                  width={38}
                />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="outcome_score" yAxisId="outcome" barSize={12} radius={[3, 3, 0, 0]}>
                  {chartData.map((entry) => (
                    <Cell key={entry.fight_sequence} fill={entry.outcome_score === 1 ? 'var(--pos)' : entry.outcome_score === -1 ? 'var(--neg)' : 'var(--ink-3)'} />
                  ))}
                </Bar>
                <Line
                  yAxisId="finish"
                  type="monotone"
                  dataKey="finish_rate"
                  stroke="var(--blue)"
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: 'var(--blue)', stroke: '#FFFFFF', strokeWidth: 1.5 }}
                  activeDot={{ r: 4, fill: 'var(--blue)', stroke: '#FFFFFF', strokeWidth: 2 }}
                  isAnimationActive
                  animationDuration={600}
                  animationEasing="ease-out"
                />
              </ComposedChart>
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
