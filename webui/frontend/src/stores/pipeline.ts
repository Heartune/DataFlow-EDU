import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { loadData } from '@/api/pipeline';
import { buildTaxonomyMapping } from '@/composables/useTaxonomyMapping';
import { computeStage1Stats, getPairCategories } from '@/composables/useStage1Stats';
import { computeQuestionStats } from '@/composables/useQuestionStats';
import type { Stage1Pair, Question } from '@/types/pipeline';
import type { Stage1Stats } from '@/composables/useStage1Stats';
import type { QuestionStats } from '@/composables/useQuestionStats';

const PAGE_SIZE = 20;

export const usePipelineStore = defineStore('pipeline', () => {
  const bookName = ref('');
  const showConfigOnly = ref(false);
  const currentStage = ref<number | null>(null);
  const taxonomySubToCat = ref<Record<string, string>>({});

  const stage1Data = ref<{ pairs?: Stage1Pair[] } | null>(null);
  const stage1Stats = ref<Stage1Stats | null>(null);
  const stage1Search = ref('');
  const stage1CatFilter = ref('');
  const stage1SubcatFilter = ref('');
  const stage1SortKey = ref('');
  const stage1SortAsc = ref(true);

  const stage2Data = ref<{ questions?: Question[] } | null>(null);
  const stage2Stats = ref<QuestionStats | null>(null);
  const stage2Search = ref('');
  const stage2LevelFilter = ref('');
  const stage2TypeFilter = ref('');
  const stage2DiffFilter = ref('');
  const stage2Page = ref(1);

  const stage3Data = ref<{ questions?: Question[] } | null>(null);
  const stage3Stats = ref<QuestionStats | null>(null);
  const stage3Search = ref('');
  const stage3LevelFilter = ref('');
  const stage3TypeFilter = ref('');
  const stage3DiffFilter = ref('');
  const stage3Page = ref(1);

  async function load(book: string) {
    const data = await loadData(book);
    taxonomySubToCat.value = buildTaxonomyMapping(data.config);

    stage1Data.value = data.stage1;
    stage1Stats.value = computeStage1Stats(data.stage1, taxonomySubToCat.value);
    stage1Search.value = '';
    stage1CatFilter.value = '';
    stage1SubcatFilter.value = '';
    stage1SortKey.value = '';
    stage1SortAsc.value = true;

    stage2Data.value = data.stage2;
    stage2Stats.value = computeQuestionStats(data.stage2.questions || []);
    stage2Search.value = '';
    stage2LevelFilter.value = '';
    stage2TypeFilter.value = '';
    stage2DiffFilter.value = '';
    stage2Page.value = 1;

    stage3Data.value = data.stage3;
    stage3Stats.value = computeQuestionStats(data.stage3.questions || []);
    stage3Search.value = '';
    stage3LevelFilter.value = '';
    stage3TypeFilter.value = '';
    stage3DiffFilter.value = '';
    stage3Page.value = 1;

    bookName.value = book;
    currentStage.value = 3;
  }

  function openConfig() {
    showConfigOnly.value = true;
    currentStage.value = 0;
  }

  function reset() {
    bookName.value = '';
    showConfigOnly.value = false;
    currentStage.value = null;
    stage1Data.value = null;
    stage1Stats.value = null;
    stage2Data.value = null;
    stage2Stats.value = null;
    stage3Data.value = null;
    stage3Stats.value = null;
  }

  const filteredStage1Pairs = computed(() => {
    let pairs = (stage1Data.value?.pairs || []).slice();
    const search = stage1Search.value.trim().toLowerCase();
    if (search) {
      pairs = pairs.filter((p) => {
        const pageStr = String(p.page_info || '').toLowerCase();
        const subStr = (p.subcategories || []).join(' ').toLowerCase();
        const catStr = getPairCategories(p, taxonomySubToCat.value).join(' ').toLowerCase();
        return pageStr.includes(search) || subStr.includes(search) || catStr.includes(search);
      });
    }
    if (stage1CatFilter.value) {
      pairs = pairs.filter((p) =>
        getPairCategories(p, taxonomySubToCat.value).includes(stage1CatFilter.value)
      );
    }
    if (stage1SubcatFilter.value) {
      pairs = pairs.filter((p) => (p.subcategories || []).includes(stage1SubcatFilter.value));
    }
    if (stage1SortKey.value === 'page') {
      pairs.sort((a, b) => {
        const va = parseInt(String(a.page_info).split('-')[0]) || 0;
        const vb = parseInt(String(b.page_info).split('-')[0]) || 0;
        return stage1SortAsc.value ? va - vb : vb - va;
      });
    } else if (stage1SortKey.value === 'count') {
      pairs.sort((a, b) => {
        const va = (a.subcategories || []).length;
        const vb = (b.subcategories || []).length;
        return stage1SortAsc.value ? va - vb : vb - va;
      });
    }
    return pairs;
  });

  function getFilteredQuestions(prefix: 'stage2' | 'stage3'): Question[] {
    const data = prefix === 'stage2' ? stage2Data.value : stage3Data.value;
    const s = prefix === 'stage2'
      ? { search: stage2Search, level: stage2LevelFilter, type: stage2TypeFilter, diff: stage2DiffFilter }
      : { search: stage3Search, level: stage3LevelFilter, type: stage3TypeFilter, diff: stage3DiffFilter };
    let qs = (data?.questions || []).slice();
    if (s.search.value)
      qs = qs.filter((q) => (q.question || '').toLowerCase().includes(s.search.value.toLowerCase()));
    if (s.level.value) qs = qs.filter((q) => q.ability_level === s.level.value);
    if (s.type.value) qs = qs.filter((q) => q.type === s.type.value);
    if (s.diff.value) qs = qs.filter((q) => q.difficulty === s.diff.value);
    return qs;
  }

  const stage2FilteredQuestions = computed(() => getFilteredQuestions('stage2'));
  const stage3FilteredQuestions = computed(() => getFilteredQuestions('stage3'));

  const stage2PaginatedQuestions = computed(() => {
    const all = stage2FilteredQuestions.value;
    const totalPages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
    if (stage2Page.value > totalPages) stage2Page.value = totalPages;
    const start = (stage2Page.value - 1) * PAGE_SIZE;
    return all.slice(start, start + PAGE_SIZE);
  });

  const stage3PaginatedQuestions = computed(() => {
    const all = stage3FilteredQuestions.value;
    const totalPages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
    if (stage3Page.value > totalPages) stage3Page.value = totalPages;
    const start = (stage3Page.value - 1) * PAGE_SIZE;
    return all.slice(start, start + PAGE_SIZE);
  });

  return {
    bookName,
    showConfigOnly,
    currentStage,
    taxonomySubToCat,
    stage1Data,
    stage1Stats,
    stage1Search,
    stage1CatFilter,
    stage1SubcatFilter,
    stage1SortKey,
    stage1SortAsc,
    stage2Data,
    stage2Stats,
    stage2Search,
    stage2LevelFilter,
    stage2TypeFilter,
    stage2DiffFilter,
    stage2Page,
    stage3Data,
    stage3Stats,
    stage3Search,
    stage3LevelFilter,
    stage3TypeFilter,
    stage3DiffFilter,
    stage3Page,
    load,
    openConfig,
    reset,
    filteredStage1Pairs,
    stage2FilteredQuestions,
    stage3FilteredQuestions,
    stage2PaginatedQuestions,
    stage3PaginatedQuestions,
    getPairCategories: (p: Stage1Pair) => getPairCategories(p, taxonomySubToCat.value),
    PAGE_SIZE,
  };
});
