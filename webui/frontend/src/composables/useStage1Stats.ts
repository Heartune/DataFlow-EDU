import type { Stage1Pair, Stage1Data } from '@/types/pipeline';

export interface Stage1Stats {
  totalPages: number;
  totalPairs: number;
  emptyPairs: number;
  subcatCount: number;
  subcatDist: Record<string, number>;
  subcatList: string[];
  catDist: Record<string, number>;
  catList: string[];
  avgSubcats: string;
}

export function computeStage1Stats(
  data: Stage1Data,
  taxonomySubToCat: Record<string, string>
): Stage1Stats {
  const pairs = data.pairs || [];
  const subcatDist: Record<string, number> = {};
  const catDist: Record<string, number> = {};
  let emptyCount = 0;
  for (const p of pairs) {
    const subs = p.subcategories || [];
    if (subs.length === 0) emptyCount++;
    for (const s of subs) {
      subcatDist[s] = (subcatDist[s] || 0) + 1;
      const cat = taxonomySubToCat[s] || '其他';
      catDist[cat] = (catDist[cat] || 0) + 1;
    }
  }
  const subcatList = Object.keys(subcatDist).sort((a, b) => subcatDist[b] - subcatDist[a]);
  const catList = Object.keys(catDist)
    .filter((k) => k)
    .sort((a, b) => {
      if (a === '其他') return 1;
      if (b === '其他') return -1;
      return catDist[b] - catDist[a];
    });
  return {
    totalPages: data.total_pages || 0,
    totalPairs: pairs.length,
    emptyPairs: emptyCount,
    subcatCount: subcatList.length,
    subcatDist,
    subcatList,
    catDist,
    catList,
    avgSubcats: pairs.length
      ? (pairs.reduce((sum, p) => sum + (p.subcategories || []).length, 0) / pairs.length).toFixed(1)
      : '0',
  };
}

export function getPairCategories(
  p: Stage1Pair,
  taxonomySubToCat: Record<string, string>
): string[] {
  const cats = [
    ...new Set((p.subcategories || []).map((s) => taxonomySubToCat[s] || '其他').filter(Boolean)),
  ];
  return cats.sort((a, b) => (a === '其他' ? 1 : b === '其他' ? -1 : 0));
}
