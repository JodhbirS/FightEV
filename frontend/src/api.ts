import type { FighterListResponse, FighterDetail } from './types';

// In production (Vercel), use the absolute backend URL.
// In local dev, Vite's proxy rewrites /api/* → http://localhost:8000/*
const API_BASE = import.meta.env.PROD
  ? 'https://fightev.onrender.com'
  : '/api';

const fighterCache = new Map<string | number, FighterDetail>();

export async function getFights() {
  const res = await fetch(`${API_BASE}/fights`);
  if (!res.ok) throw new Error("Failed to fetch /fights");
  return await res.json();
}

export async function getFighters(
  limit: number = 20,
  offset: number = 0,
  search: string = '',
): Promise<FighterListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search) params.set('search', search);

  const res = await fetch(`${API_BASE}/fighters?${params}`);
  if (!res.ok) throw new Error("Failed to fetch /fighters");
  return await res.json();
}

export async function getFighter(id: number): Promise<FighterDetail> {
  if (fighterCache.has(id)) {
    return fighterCache.get(id)!;
  }
  const res = await fetch(`${API_BASE}/fighters/${id}`);
  if (!res.ok) {
    if (res.status === 404) throw new Error("Fighter not found");
    throw new Error("Failed to fetch fighter details");
  }
  const data = await res.json();
  fighterCache.set(id, data);
  fighterCache.set(data.name.toLowerCase(), data);
  return data;
}

export async function getFighterByName(name: string): Promise<FighterDetail> {
  const key = name.toLowerCase().trim();
  if (fighterCache.has(key)) {
    return fighterCache.get(key)!;
  }
  const res = await fetch(`${API_BASE}/fighters/by-name/${encodeURIComponent(name)}`);
  if (!res.ok) {
    if (res.status === 404) throw new Error("Fighter not found");
    throw new Error("Failed to fetch fighter details");
  }
  const data = await res.json();
  fighterCache.set(key, data);
  fighterCache.set(data.id, data);
  return data;
}