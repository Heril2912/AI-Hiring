import { apiFetch } from "./client";

export interface OccupationSearchItem {
  conceptId: string;
  onetSocCode: string;
  canonicalTitle: string;
  matchedAlias?: string | null;
  source: string;
  sourceVersion: string;
}

export interface SkillSearchItem {
  conceptId: string;
  canonicalLabel: string;
  matchedAlias?: string | null;
  category?: string | null;
  source: string;
  sourceVersion?: string | null;
}

export async function searchOccupations(query: string, limit: number = 10): Promise<OccupationSearchItem[]> {
  const trimmed = query.trim();
  if (!trimmed) return [];
  const params = new URLSearchParams({
    q: trimmed,
    limit: String(limit),
  });
  return apiFetch<OccupationSearchItem[]>(`/api/v1/taxonomy/occupations?${params.toString()}`);
}

export async function searchSkills(query: string, limit: number = 10): Promise<SkillSearchItem[]> {
  const trimmed = query.trim();
  if (!trimmed) return [];
  const params = new URLSearchParams({
    q: trimmed,
    limit: String(limit),
  });
  return apiFetch<SkillSearchItem[]>(`/api/v1/taxonomy/skills?${params.toString()}`);
}
