import type { CaseRecord } from "./types";

const KEY = "coreaigent.recent-cases.v1";

export function loadCases(): CaseRecord[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function saveCase(record: CaseRecord): CaseRecord[] {
  const cases = loadCases();
  const next = [record, ...cases.filter((item) => item.caseId !== record.caseId)]
    .sort((a, b) => Date.parse(b.updatedAt ?? b.createdAt) - Date.parse(a.updatedAt ?? a.createdAt))
    .slice(0, 30);
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function updateStoredCase(caseId: string, updates: Partial<CaseRecord>): CaseRecord[] {
  const current = loadCases();
  const match = current.find((item) => item.caseId === caseId);
  if (!match) return current;
  return saveCase({ ...match, ...updates });
}
