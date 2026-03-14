import type { Question } from '@/types/pipeline';

export interface QuestionStats {
  total: number;
  levelDist: Record<string, number>;
  typeDist: Record<string, number>;
  diffDist: Record<string, number>;
  categoryDist: Record<string, number>;
  subcategoryDist: Record<string, number>;
  abilityMainDist: Record<string, number>;
  subjectiveRatio: string;
}

export function computeQuestionStats(questions: Question[]): QuestionStats {
  const total = questions.length;
  const levelDist: Record<string, number> = {};
  const typeDist: Record<string, number> = {};
  const diffDist: Record<string, number> = { 易: 0, 中: 0, 难: 0 };
  const categoryDist: Record<string, number> = {};
  const subcategoryDist: Record<string, number> = {};
  const abilityMainDist: Record<string, number> = {};
  for (const q of questions) {
    const l = q.ability_level || '未分类';
    levelDist[l] = (levelDist[l] || 0) + 1;
    const t = q.type || '未知';
    typeDist[t] = (typeDist[t] || 0) + 1;
    const d = q.difficulty || '中';
    if (diffDist[d] !== undefined) diffDist[d]++;
    const cat = q.category || '未分类';
    categoryDist[cat] = (categoryDist[cat] || 0) + 1;
    const subcat = q.subcategory || '未分类';
    subcategoryDist[subcat] = (subcategoryDist[subcat] || 0) + 1;
    const main = q.ability_main || '未分类';
    abilityMainDist[main] = (abilityMainDist[main] || 0) + 1;
  }
  const subjective = ['简答题', '论述题', '计算题', '综合题'];
  const subjCount = subjective.reduce((s, f) => s + (typeDist[f] || 0), 0);
  return {
    total,
    levelDist,
    typeDist,
    diffDist,
    categoryDist,
    subcategoryDist,
    abilityMainDist,
    subjectiveRatio: total ? String(Math.round((subjCount / total) * 100)) : '0',
  };
}
