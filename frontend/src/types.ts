// --- Existing fight card types ---

export interface FightOut {
  fighter1: string;
  fighter2: string;
  odds1: number;
  odds2: number;
  modelProb1: number;
  modelProb2: number;
  impProb1: number;
  impProb2: number;
  ev1: number;
  ev2: number;
  predWinner: number;
  predMethod: string;
  predMethodProb: number;
  kelly1?: number;
  kelly2?: number;
}

// --- Fighter types ---

export interface FighterListItem {
  id: number;
  name: string;
  weight_class: string | null;
  is_active?: boolean;
}

export interface FighterListResponse {
  total: number;
  limit: number;
  offset: number;
  fighters: FighterListItem[];
}

export interface ModelPoint {
  fight_id: number;
  fight_sequence: number;
  opponent_name: string;
  result: string;
  finish: boolean;
  finish_rate: number;
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
  is_active?: boolean;
  total_fights: number;
  wins: number;
  losses: number;
  draws: number;
  fight_history: FightHistoryItem[];
  model_history: ModelPoint[];
}
