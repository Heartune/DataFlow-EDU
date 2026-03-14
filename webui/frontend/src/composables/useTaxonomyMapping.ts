import type { EduConfig } from '@/types/pipeline';

export function buildTaxonomyMapping(config: EduConfig | null): Record<string, string> {
  const map: Record<string, string> = {};
  if (!config?.taxonomy) return map;
  for (const t of config.taxonomy) {
    const cat = t.name || '';
    for (const s of t.subcategories || []) {
      map[s] = cat;
    }
  }
  return map;
}
