// --- Existing fight card types ---

export interface FightOut {
  fighter1: string;
  fighter2: string;
  odds1: number;
  odds2: number;
  eloProb1: number;
  eloProb2: number;
  impProb1: number;
  impProb2: number;
  ev1: number;
  ev2: number;
  predWinner: number;
  kelly1?: number;
  kelly2?: number;
}

// --- Fighter types ---

export interface FighterListItem {
  id: number;
  name: string;
  weight_class: string | null;
  current_elo: number;
  is_active?: boolean;
}

export interface FighterListResponse {
  total: number;
  limit: number;
  offset: number;
  fighters: FighterListItem[];
}

export interface EloPoint {
  fight_id: number;
  fight_sequence: number;
  elo_after: number;
  opponent_name: string;
  result: string;
  event: string;
}

export interface FightHistoryItem {
  id: number;
  event: string;
  opponent_name: string;
  result: string;
  method: string;
  round: number;
  time: string;
}

export interface FighterDetail {
  id: number;
  name: string;
  weight_class: string | null;
  current_elo: number;
  is_active?: boolean;
  total_fights: number;
  wins: number;
  losses: number;
  draws: number;
  fight_history: FightHistoryItem[];
  elo_history: EloPoint[];
}
