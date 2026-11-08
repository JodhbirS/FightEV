import type { FightOut, FighterListResponse, FighterDetail } from './types';

// In production (Vercel), use the absolute backend URL.
// In local dev, Vite's proxy rewrites /api/* → http://localhost:8000/*
const API_BASE = import.meta.env.PROD
  ? 'https://fightev.onrender.com'
  : '/api';
const REQUEST_TIMEOUT_MS = 90_000;

const fighterCache = new Map<string | number, FighterDetail>();

class ApiError extends Error {
  constructor(public readonly status: number) {
    super(`Request failed (${status})`);
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    if (!res.ok) throw new ApiError(res.status);
    return await res.json() as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('The API took too long to respond. Please try again.');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getFights() {
  return fetchJson<FightOut[]>('/fights');
}

export async function getFighters(
  limit: number = 20,
  offset: number = 0,
  search: string = '',
  division: string = '',
): Promise<FighterListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search) params.set('search', search);
  if (division) params.set('division', division);
  return fetchJson<FighterListResponse>(`/fighters?${params}`);
}

export async function getFighter(id: number): Promise<FighterDetail> {
  if (fighterCache.has(id)) {
    return fighterCache.get(id)!;
  }
  let data: FighterDetail;
  try {
    data = await fetchJson<FighterDetail>(`/fighters/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) throw new Error("Fighter not found");
    throw new Error("Failed to fetch fighter details", { cause: error });
  }
  fighterCache.set(id, data);
  fighterCache.set(data.name.toLowerCase(), data);
  return data;
}

export async function getFighterByName(name: string): Promise<FighterDetail> {
  const key = name.toLowerCase().trim();
  if (fighterCache.has(key)) {
    return fighterCache.get(key)!;
  }
  let data: FighterDetail;
  try {
    data = await fetchJson<FighterDetail>(`/fighters/by-name/${encodeURIComponent(name)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) throw new Error("Fighter not found");
    throw new Error("Failed to fetch fighter details", { cause: error });
  }
  fighterCache.set(key, data);
  fighterCache.set(data.id, data);
  return data;
}