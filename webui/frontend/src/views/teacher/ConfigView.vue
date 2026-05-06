<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '@/api/client';

const props = defineProps<{
  id: string;
  taskStatus?: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  taskName?: string;
}>();

const router = useRouter();

const PRESET_LABELS: Record<string, string> = {
  senior_biology: '高中生物',
  senior_chinese: '高中语文',
  senior_history: '高中历史',
  senior_math: '高中数学',
  senior_physics: '高中物理',
  senior_english: '高中英语',
  senior_chemistry: '高中化学',
  senior_politics: '高中政治',
  senior_geography: '高中地理',
  junior_chinese: '初中语文',
  junior_math: '初中数学',
  junior_english: '初中英语',
  junior_physics: '初中物理',
  junior_chemistry: '初中化学',
  junior_biology: '初中生物',
  junior_politics: '初中道德与法治',
  junior_history: '初中历史',
  junior_geography: '初中地理',
};

const PRESET_SUBJECT_ORDER = [
  'chinese',
  'math',
  'english',
  'physics',
  'chemistry',
  'biology',
  'politics',
  'history',
  'geography',
];

/** 预设 id 中的学科段：senior_chinese / junior_chinese → chinese（高中与初中同一学科必须同色） */
function presetSubjectSlug(id: string): string {
  const m = id.match(/^(?:senior|junior)_(.+)$/);
  return m?.[1] ?? '';
}

/** 学科 tiles 前置图标：单字徽章，与课表简称一致 */
const PRESET_SUBJECT_BADGE: Record<string, string> = {
  chinese: '语',
  math: '数',
  english: '英',
  physics: '物',
  chemistry: '化',
  biology: '生',
  politics: '政',
  history: '史',
  geography: '地',
};

/** 各学科莫兰迪渐变（仅按学科 key，不按学段；九门色相互斥、高中/初中共用） */
const PRESET_SUBJECT_BADGE_LOGO: Record<string, string> = {
  chinese: 'bg-gradient-to-br from-rose-200 via-rose-100 to-stone-300 text-rose-900/80 shadow-sm shadow-stone-900/5',
  math: 'bg-gradient-to-br from-sky-200 via-slate-100 to-slate-300 text-slate-800 shadow-sm shadow-slate-900/5',
  english: 'bg-gradient-to-br from-violet-200 via-purple-50 to-stone-300 text-violet-900/75 shadow-sm shadow-stone-900/5',
  physics: 'bg-gradient-to-br from-cyan-200 via-sky-50 to-slate-300 text-cyan-900/78 shadow-sm shadow-slate-900/5',
  chemistry: 'bg-gradient-to-br from-orange-200 via-amber-50 to-stone-300 text-orange-950/75 shadow-sm shadow-stone-900/5',
  biology: 'bg-gradient-to-br from-emerald-200 via-lime-50 to-stone-200 text-emerald-900/78 shadow-sm shadow-stone-900/5',
  politics: 'bg-gradient-to-br from-indigo-200 via-slate-100 to-stone-300 text-indigo-900/80 shadow-sm shadow-slate-900/5',
  history: 'bg-gradient-to-br from-amber-100 via-yellow-100 to-stone-300 text-amber-950/72 shadow-sm shadow-stone-900/5',
  geography: 'bg-gradient-to-br from-teal-200 via-cyan-50 to-stone-200 text-teal-900/76 shadow-sm shadow-stone-900/5',
};

function presetSubjectBadgeChar(id: string): string {
  return PRESET_SUBJECT_BADGE[presetSubjectSlug(id)] ?? '?';
}

function presetSubjectBadgeLogoClass(id: string, selected: boolean): string {
  const slug = presetSubjectSlug(id);
  const palette =
    PRESET_SUBJECT_BADGE_LOGO[slug] ??
    'bg-gradient-to-br from-stone-200 via-slate-100 to-slate-300 text-slate-700 shadow-sm shadow-stone-900/5';
  const ring = selected ? ' ring-2 ring-stone-500/35 ring-offset-2 ring-offset-slate-50' : '';
  return `flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-xs font-bold leading-none transition ${palette}${ring}`;
}

type SourceType = 'official_preset' | 'user_template' | 'recent' | 'custom';
type SuggestTarget = 'taxonomy' | 'ability_levels' | 'question_types';

interface AbilityLevel {
  name: string;
  weight: number;
  description?: string;
  sublevels?: string[];
}

interface QuestionType {
  name: string;
  weight: number;
}

interface TaxonomyItem {
  name: string;
  subcategories: string[];
}

interface DifficultyDist {
  easy: number;
  medium: number;
  hard: number;
}

interface ConfigSnapshot {
  preset?: string | null;
  source_type?: SourceType;
  source_id?: string | null;
  grade?: string;
  subject?: string;
  taxonomy?: TaxonomyItem[];
  ability_levels?: AbilityLevel[];
  question_types?: QuestionType[];
  difficulty_distribution?: DifficultyDist;
  default_difficulty_distribution?: Record<string, number>;
  enabled_stages?: string[];
}

interface SavedConfigItem {
  id: string;
  name: string;
  config: ConfigSnapshot;
  updated_at?: number;
  used_at?: number;
  source_type?: string;
  source_id?: string | null;
}

interface OptionalStage {
  name: string;
  desc: string;
  pairName: string | null;
}

const OPTIONAL_STAGES: OptionalStage[] = [
  { name: '2.2 知识均衡检查与修正', desc: '检查题目在各认知层级与知识领域的分布，并自动补题修正偏差', pairName: null },
  { name: '3.1 题意模糊检查', desc: '识别表述不清晰的题目并标记，为下一步修正做准备', pairName: '3.2 题意模糊修正' },
  { name: '3.2 题意模糊修正', desc: '对标记为模糊的题目重新润色，使题意清晰准确', pairName: '3.1 题意模糊检查' },
  { name: '3.3 考察领域检查', desc: '校验题目所考察的知识点是否与教材范围吻合', pairName: '3.4 考察领域修正' },
  { name: '3.4 考察领域修正', desc: '修正与教材范围不符或跑题的题目', pairName: '3.3 考察领域检查' },
  { name: '3.5 去除重复题目', desc: '检测并剔除语义高度相似的重复题目', pairName: null },
  { name: '3.6 解析生成', desc: '使用 AI 为每道题生成详细解题步骤（解析）', pairName: null },
  { name: '3.7 多语言翻译', desc: '将题目翻译为英文、法文等多语言版本', pairName: null },
  { name: '3.8 选择题格式检查', desc: '校验选择题的选项格式与答案标注是否规范', pairName: null },
];

const ALL_OPTIONAL_NAMES = new Set(OPTIONAL_STAGES.map((s) => s.name));
const OPTIONAL_STAGE_NAME_ALIASES: Record<string, string> = {
  '3.6 题库增强': '3.6 解析生成',
};
const DEFAULT_DISABLED = new Set(['3.7 多语言翻译']);
const totalSteps = 6;
const NEEDS_MAX = 500;
/** 默认题型占比强度 0–100（与旧版 0.25:0.15… 同比例）；持久化仍为 weight，生成按总和归一化。 */
const DEFAULT_CUSTOM_QUESTION_TYPES: QuestionType[] = [
  { name: '选择题', weight: 25 },
  { name: '填空题', weight: 15 },
  { name: '判断题', weight: 10 },
  { name: '简答题', weight: 25 },
  { name: '综合题', weight: 25 },
];
const DEFAULT_ENABLED_STAGES = OPTIONAL_STAGES.map((s) => s.name).filter((n) => !DEFAULT_DISABLED.has(n));

function normalizeOptionalStageName(name: unknown): string | null {
  if (typeof name !== 'string') return null;
  const normalized = OPTIONAL_STAGE_NAME_ALIASES[name] ?? name;
  return ALL_OPTIONAL_NAMES.has(normalized) ? normalized : null;
}

const presets = ref<string[]>([]);
const templates = ref<SavedConfigItem[]>([]);
const recents = ref<SavedConfigItem[]>([]);
const presetsLoading = ref(false);
const libraryLoading = ref(false);

const selectedPreset = ref('');
const sourceType = ref<SourceType>('custom');
const sourceId = ref<string | null>(null);
const sourceName = ref('新建自定义配置');
const grade = ref('');
const subject = ref('');
const taxonomy = ref<TaxonomyItem[]>([]);
const abilityLevels = ref<AbilityLevel[]>([]);
const questionTypes = ref<QuestionType[]>(DEFAULT_CUSTOM_QUESTION_TYPES.map((q) => ({ ...q })));
const difficulty = ref<DifficultyDist>({ easy: 30, medium: 50, hard: 20 });
const enabledStages = ref<Set<string>>(
  new Set(DEFAULT_ENABLED_STAGES),
);

const step = ref(1);
const error = ref('');
const info = ref('');
const submitting = ref(false);
const presetLoading = ref(false);
const saveTemplateOpen = ref(false);
const templateName = ref('');
let infoDismissTimer: ReturnType<typeof setTimeout> | null = null;

const suggestOpen = ref(false);
const suggestTarget = ref<SuggestTarget>('taxonomy');
const suggestNeeds = ref('');
const suggestLoading = ref(false);
const suggestError = ref('');
const suggestItems = ref<unknown[]>([]);
const suggestState = reactive({ source: '' as 'live' | '' });

const readonly = computed(() => props.taskStatus === 'running' || props.taskStatus === 'succeeded');
const showCustomTemplatePrompt = computed(() => step.value === 5 && !readonly.value && sourceType.value === 'custom');

function presetSubjectSortKey(id: string): number {
  const m = id.match(/^(?:senior|junior)_(.+)$/);
  if (!m) return PRESET_SUBJECT_ORDER.length;
  const i = PRESET_SUBJECT_ORDER.indexOf(m[1]);
  return i === -1 ? PRESET_SUBJECT_ORDER.length : i;
}

function sortPresetsBySubject(ids: string[]): string[] {
  return [...ids].sort(
    (a, b) => presetSubjectSortKey(a) - presetSubjectSortKey(b) || a.localeCompare(b),
  );
}

function presetLabel(id: string): string {
  return PRESET_LABELS[id] ?? id;
}

const seniorPresets = computed(() =>
  sortPresetsBySubject(presets.value.filter((p) => p.startsWith('senior_'))),
);
const juniorPresets = computed(() =>
  sortPresetsBySubject(presets.value.filter((p) => p.startsWith('junior_'))),
);

const sumQuestionTypes = computed(() =>
  questionTypes.value.reduce((s, q) => s + (Number(q.weight) || 0), 0),
);
const sumDifficulty = computed(
  () =>
    (Number(difficulty.value.easy) || 0) +
    (Number(difficulty.value.medium) || 0) +
    (Number(difficulty.value.hard) || 0),
);
const canNext = computed(() => {
  if (step.value === 1) return !!grade.value.trim() && !!subject.value.trim() && !presetLoading.value;
  if (
    step.value === 4 &&
    !readonly.value &&
    questionTypes.value.length > 0 &&
    sumQuestionTypes.value <= 0
  ) {
    return false;
  }
  if (step.value === 5 && !readonly.value && sumDifficulty.value <= 0) {
    return false;
  }
  return true;
});

const selectedSourceSummary = computed(() => {
  const g = grade.value.trim() || '未填写学段';
  const s = subject.value.trim() || '未填写学科';
  return `${sourceName.value} · ${g} · ${s}`;
});

const presetColors = ['bg-rose-300', 'bg-amber-300', 'bg-emerald-300', 'bg-sky-300', 'bg-purple-300', 'bg-pink-300', 'bg-orange-300'];
const qtBars = computed(() => {
  const total = sumQuestionTypes.value || 1;
  return questionTypes.value.map((q, i) => ({
    name: q.name,
    pct: ((Number(q.weight) || 0) / total) * 100,
    color: presetColors[i % presetColors.length],
  }));
});

function showTransientInfo(message: string, ms = 3000) {
  if (infoDismissTimer) clearTimeout(infoDismissTimer);
  info.value = message;
  infoDismissTimer = setTimeout(() => {
    info.value = '';
    infoDismissTimer = null;
  }, ms);
}

function difficultyFromConfig(cfg: ConfigSnapshot): DifficultyDist {
  const direct = cfg.difficulty_distribution;
  if (direct) {
    return {
      easy: questionTypeWeightFromStored(direct.easy ?? 0.3),
      medium: questionTypeWeightFromStored(direct.medium ?? 0.5),
      hard: questionTypeWeightFromStored(direct.hard ?? 0.2),
    };
  }
  const d = cfg.default_difficulty_distribution;
  return {
    easy: questionTypeWeightFromStored(d?.easy ?? d?.['易'] ?? 0.3),
    medium: questionTypeWeightFromStored(d?.medium ?? d?.['中'] ?? 0.5),
    hard: questionTypeWeightFromStored(d?.hard ?? d?.['难'] ?? 0.2),
  };
}

function normalizeTaxonomy(raw: unknown): TaxonomyItem[] {
  return Array.isArray(raw)
    ? raw.map((t: any) => ({
        name: String(t?.name || ''),
        subcategories: Array.isArray(t?.subcategories) ? t.subcategories.map(String) : [],
      }))
    : [];
}

function normalizeAbility(raw: unknown): AbilityLevel[] {
  return Array.isArray(raw)
    ? raw.map((a: any) => ({
        name: String(a?.name || ''),
        weight: Number(a?.weight ?? 0.25),
        description: String(a?.description || ''),
        sublevels: Array.isArray(a?.sublevels) ? a.sublevels.map(String) : [],
      }))
    : [];
}

/**
 * 配置里 question_type.weight → 向导「占比强度」0–100。
 * 大于 1 或已为整数：按原样取整（上限 100）；否则视为旧版 0~1 小数并 ×100（如 0.25→25）。
 */
function questionTypeWeightFromStored(w: unknown): number {
  const n = Number(w ?? 0.25);
  if (!Number.isFinite(n) || n < 0) return 0;
  let v: number;
  if (n > 1 || Number.isInteger(n)) v = Math.round(n);
  else v = Math.round(n * 100);
  return Math.max(0, Math.min(100, v));
}

function normalizeQuestionTypes(raw: unknown): QuestionType[] {
  return Array.isArray(raw)
    ? raw.map((q: any) => ({
        name: String(q?.name || ''),
        weight: questionTypeWeightFromStored(q?.weight ?? 0.25),
      }))
    : [];
}

function cloneDefaultCustomQuestionTypes(): QuestionType[] {
  return DEFAULT_CUSTOM_QUESTION_TYPES.map((q) => ({ ...q }));
}

function buildBlankCustomConfig(): ConfigSnapshot {
  return {
    preset: null,
    source_type: 'custom',
    source_id: null,
    grade: '',
    subject: '',
    taxonomy: [],
    ability_levels: [],
    question_types: cloneDefaultCustomQuestionTypes(),
    difficulty_distribution: { easy: 30, medium: 50, hard: 20 },
    enabled_stages: [...DEFAULT_ENABLED_STAGES],
  };
}

function hasUsableQuestionTypes(items: QuestionType[]): boolean {
  return items.some((q) => q.name.trim());
}

function shouldBackfillCustomQuestionTypes(
  cfg: ConfigSnapshot,
  meta: { type: SourceType; id?: string | null; name: string },
): boolean {
  if (cfg.source_type === 'custom' || meta.type === 'custom') return true;
  return !cfg.preset && meta.type !== 'official_preset';
}

function ensureCustomQuestionTypes() {
  if (sourceType.value !== 'official_preset' && !hasUsableQuestionTypes(questionTypes.value)) {
    questionTypes.value = cloneDefaultCustomQuestionTypes();
  }
}

function applyConfigSnapshot(cfg: ConfigSnapshot, meta: { type: SourceType; id?: string | null; name: string }) {
  sourceType.value = meta.type;
  sourceId.value = meta.id ?? null;
  sourceName.value = meta.name;
  selectedPreset.value = meta.type === 'official_preset' ? String(meta.id || cfg.preset || '') : String(cfg.preset || '');
  grade.value = String(cfg.grade || '');
  subject.value = String(cfg.subject || '');
  taxonomy.value = normalizeTaxonomy(cfg.taxonomy);
  abilityLevels.value = normalizeAbility(cfg.ability_levels);
  const normalizedQuestionTypes = normalizeQuestionTypes(cfg.question_types);
  questionTypes.value =
    hasUsableQuestionTypes(normalizedQuestionTypes) || !shouldBackfillCustomQuestionTypes(cfg, meta)
      ? normalizedQuestionTypes
      : cloneDefaultCustomQuestionTypes();
  difficulty.value = difficultyFromConfig(cfg);
  if (Array.isArray(cfg.enabled_stages)) {
    enabledStages.value = new Set(
      cfg.enabled_stages
        .map(normalizeOptionalStageName)
        .filter((n): n is string => Boolean(n)),
    );
  }
  step.value = 1;
  saveTemplateOpen.value = false;
}

function buildCurrentConfig(): ConfigSnapshot {
  return {
    preset: selectedPreset.value || null,
    source_type: sourceType.value,
    source_id: sourceId.value,
    grade: grade.value.trim(),
    subject: subject.value.trim(),
    taxonomy: taxonomy.value,
    ability_levels: abilityLevels.value,
    question_types:
      sourceType.value !== 'official_preset' && !hasUsableQuestionTypes(questionTypes.value)
        ? cloneDefaultCustomQuestionTypes()
        : questionTypes.value,
    difficulty_distribution: difficulty.value,
    enabled_stages: [...enabledStages.value],
  };
}

async function loadPresets() {
  presetsLoading.value = true;
  try {
    const { data } = await api.get('/config/presets');
    presets.value = Array.isArray(data) ? data : [];
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载预设失败';
  } finally {
    presetsLoading.value = false;
  }
}

async function loadUserLibrary() {
  libraryLoading.value = true;
  try {
    const [templateResp, recentResp] = await Promise.all([
      api.get('/user-config/templates'),
      api.get('/user-config/recents', { params: { limit: 5 } }),
    ]);
    templates.value = Array.isArray(templateResp.data) ? templateResp.data : [];
    recents.value = Array.isArray(recentResp.data) ? recentResp.data : [];
  } catch {
    templates.value = [];
    recents.value = [];
  } finally {
    libraryLoading.value = false;
  }
}

async function applyPreset(name: string) {
  if (!name || readonly.value) return;
  if (sourceType.value === 'official_preset' && selectedPreset.value === name) {
    error.value = '';
    applyConfigSnapshot(buildBlankCustomConfig(), { type: 'custom', id: null, name: '新建自定义配置' });
    return;
  }
  presetLoading.value = true;
  error.value = '';
  try {
    const { data } = await api.get(`/config/presets/${encodeURIComponent(name)}`);
    applyConfigSnapshot(
      {
        ...data,
        preset: name,
        source_type: 'official_preset',
        source_id: name,
      },
      { type: 'official_preset', id: name, name: presetLabel(name) },
    );
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载预设失败';
  } finally {
    presetLoading.value = false;
  }
}

function applySaved(item: SavedConfigItem, type: 'user_template' | 'recent') {
  if (readonly.value) return;
  applyConfigSnapshot(item.config, { type, id: item.id, name: item.name });
  showTransientInfo(`已载入 ${item.name}`);
}

function createCustom() {
  if (readonly.value) return;
  error.value = '';
  applyConfigSnapshot(buildBlankCustomConfig(), { type: 'custom', id: null, name: '新建自定义配置' });
}

async function loadExistingConfig() {
  try {
    const { data } = await api.get(`/tasks/${props.id}/config`);
    if (data?.exists && data.config) {
      const cfg = data.config as ConfigSnapshot;
      const id = cfg.source_id || cfg.preset || null;
      const type = cfg.source_type || (cfg.preset ? 'official_preset' : 'custom');
      const name = type === 'official_preset' && id ? presetLabel(id) : '已保存任务配置';
      applyConfigSnapshot(cfg, { type, id, name });
    }
  } catch {
    /* ignore */
  }
}

function next() {
  if (
    step.value === 4 &&
    !readonly.value &&
    questionTypes.value.length > 0 &&
    sumQuestionTypes.value <= 0
  ) {
    error.value = '请至少为一种题型拉高占比强度（大于 0），或删掉不参与生成的题型。';
    return;
  }
  if (step.value === 5 && !readonly.value && sumDifficulty.value <= 0) {
    error.value = '请至少调高易/中/难中一档的占比强度，再进入下一步。';
    return;
  }
  error.value = '';
  if (step.value < totalSteps) step.value += 1;
}
function prev() {
  if (step.value > 1) step.value -= 1;
}

function addTaxonomy() {
  taxonomy.value.push({ name: '新知识大类', subcategories: ['新知识小类'] });
}
function removeTaxonomy(idx: number) {
  taxonomy.value.splice(idx, 1);
}
function addSubcategory(item: TaxonomyItem) {
  item.subcategories.push('新知识小类');
}
function removeSubcategory(item: TaxonomyItem, idx: number) {
  item.subcategories.splice(idx, 1);
}
function addAbility() {
  abilityLevels.value.push({ name: '新核心素养', weight: 0.25, description: '', sublevels: [] });
}
function removeAbility(idx: number) {
  abilityLevels.value.splice(idx, 1);
}
function removeSublevel(level: AbilityLevel, idx: number) {
  level.sublevels = (level.sublevels || []).filter((_, i) => i !== idx);
}
function addSublevel(level: AbilityLevel) {
  const subs = level.sublevels || (level.sublevels = []);
  subs.push('新子层级');
}
function removeQT(idx: number) {
  questionTypes.value.splice(idx, 1);
}
function addQT() {
  questionTypes.value.push({ name: '新题型', weight: 20 });
}
/** 滑条 0–100：超出范围时夹取并取整，便于与旧数据或粘贴值兼容。 */
function clampQtPercentStrength(q: QuestionType) {
  let v = Number(q.weight);
  if (!Number.isFinite(v)) v = 0;
  q.weight = Math.max(0, Math.min(100, Math.round(v)));
}
function clampDifficultyStrength(key: 'easy' | 'medium' | 'hard') {
  let v = Number(difficulty.value[key]);
  if (!Number.isFinite(v)) v = 0;
  difficulty.value[key] = Math.max(0, Math.min(100, Math.round(v)));
}
function toggleStage(s: OptionalStage) {
  if (readonly.value) return;
  const nextSet = new Set(enabledStages.value);
  if (nextSet.has(s.name)) {
    nextSet.delete(s.name);
    if (s.pairName) nextSet.delete(s.pairName);
  } else {
    nextSet.add(s.name);
    if (s.pairName) nextSet.add(s.pairName);
  }
  enabledStages.value = nextSet;
}

function openSuggest(target: SuggestTarget) {
  if (!grade.value.trim() || !subject.value.trim()) {
    error.value = '请先填写学段和学科';
    step.value = 1;
    return;
  }
  suggestTarget.value = target;
  suggestOpen.value = true;
  suggestError.value = '';
  suggestItems.value = [];
  suggestNeeds.value = '';
  suggestState.source = '';
}

function closeSuggest() {
  suggestOpen.value = false;
  suggestLoading.value = false;
}

async function fetchSuggest() {
  suggestError.value = '';
  if (suggestNeeds.value.length > NEEDS_MAX) {
    suggestError.value = `个性化需求最长 ${NEEDS_MAX} 字`;
    return;
  }
  suggestLoading.value = true;
  try {
    const { data } = await api.post('/config/suggest', {
      target: suggestTarget.value,
      grade: grade.value.trim(),
      subject: subject.value.trim(),
      book: props.taskName || '未指定教材',
      needs: suggestNeeds.value.trim(),
    });
    const items = Array.isArray(data?.items) ? data.items : [];
    if (!items.length) {
      suggestError.value = '联网模型未返回有效建议，请稍后重试或缩短个性化需求';
      return;
    }
    suggestItems.value = items;
    suggestState.source = 'live';
  } catch (err: any) {
    const code = err?.response?.data?.error;
    const msg = err?.response?.data?.message;
    if (code === 'missing_llm_key') suggestError.value = 'LLM Key 未配置，请联系管理员';
    else if (code === 'rate_limited') suggestError.value = msg || '调用过于频繁，请稍后再试';
    else if (err?.response?.status === 504) suggestError.value = '联网 LLM 调用超时（30s），请稍后再试';
    else suggestError.value = msg || code || err?.message || '联网建议失败';
  } finally {
    suggestLoading.value = false;
  }
}

function mergeTaxonomy(items: TaxonomyItem[]) {
  const map = new Map(taxonomy.value.map((t) => [t.name, t]));
  for (const item of items) {
    const name = String(item.name || '').trim();
    if (!name) continue;
    const existing = map.get(name);
    if (!existing) {
      const nextItem = { name, subcategories: [...(item.subcategories || [])] };
      taxonomy.value.push(nextItem);
      map.set(name, nextItem);
    } else {
      for (const sub of item.subcategories || []) {
        if (sub && !existing.subcategories.includes(sub)) existing.subcategories.push(sub);
      }
    }
  }
}

function mergeAbility(items: AbilityLevel[]) {
  const map = new Map(abilityLevels.value.map((a) => [a.name, a]));
  for (const item of items) {
    const name = String(item.name || '').trim();
    if (!name) continue;
    const existing = map.get(name);
    if (!existing) {
      const nextItem = {
        name,
        weight: Number(item.weight ?? 0.25),
        description: item.description || '',
        sublevels: [...(item.sublevels || [])],
      };
      abilityLevels.value.push(nextItem);
      map.set(name, nextItem);
    } else {
      if (!existing.description && item.description) existing.description = item.description;
      const subs = existing.sublevels || (existing.sublevels = []);
      for (const sub of item.sublevels || []) {
        if (sub && !subs.includes(sub)) subs.push(sub);
      }
    }
  }
}

function mergeQuestionTypes(items: QuestionType[]) {
  const map = new Map(questionTypes.value.map((q) => [q.name, q]));
  for (const item of items) {
    const name = String(item.name || '').trim();
    if (!name) continue;
    if (!map.has(name))
      questionTypes.value.push({ name, weight: questionTypeWeightFromStored(item.weight ?? 0.1) });
  }
}

function applySuggestions(mode: 'merge' | 'replace') {
  if (suggestTarget.value === 'taxonomy') {
    const items = normalizeTaxonomy(suggestItems.value);
    if (mode === 'replace') taxonomy.value = items;
    else mergeTaxonomy(items);
  } else if (suggestTarget.value === 'ability_levels') {
    const items = normalizeAbility(suggestItems.value);
    if (mode === 'replace') abilityLevels.value = items;
    else mergeAbility(items);
  } else {
    const items = normalizeQuestionTypes(suggestItems.value);
    if (mode === 'replace') questionTypes.value = items;
    else mergeQuestionTypes(items);
  }
  showTransientInfo(mode === 'replace' ? '已替换为联网建议' : '已合并联网建议');
  closeSuggest();
}

function validateBeforeSave(): boolean {
  if (!grade.value.trim() || !subject.value.trim()) {
    error.value = '请先填写学段和学科';
    step.value = 1;
    return false;
  }
  ensureCustomQuestionTypes();
  if (
    sourceType.value !== 'official_preset' &&
    hasUsableQuestionTypes(questionTypes.value) &&
    sumQuestionTypes.value <= 0
  ) {
    error.value = '题型占比强度不能全为 0，请至少调高一种题型的滑条或占比。';
    step.value = 4;
    return false;
  }
  if (sumDifficulty.value <= 0) {
    error.value = '难度占比强度不能全为 0，请至少调高一档滑条。';
    step.value = 5;
    return false;
  }
  return true;
}

async function postConfig() {
  const cfg = buildCurrentConfig();
  await api.post(`/tasks/${props.id}/config`, {
    preset: sourceType.value === 'official_preset' ? selectedPreset.value : null,
    source_type: sourceType.value,
    source_id: sourceId.value,
    name: `${grade.value.trim()}${subject.value.trim()}`,
    overrides: cfg,
  });
}

async function saveAndRun() {
  if (!validateBeforeSave()) return;
  submitting.value = true;
  error.value = '';
  try {
    await postConfig();
    await loadUserLibrary();
    if (!readonly.value) await api.post(`/tasks/${props.id}/run`);
    router.replace(`/teacher/tasks/${props.id}`);
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'task_already_running') error.value = '任务已在运行中';
    else if (code === 'user_has_running_task') error.value = '你已有任务在跑，等它结束后再启动新任务';
    else if (code === 'missing_llm_key') error.value = 'LLM Key 未配置，请联系管理员';
    else error.value = err?.response?.data?.message || err?.message || '提交失败';
  } finally {
    submitting.value = false;
  }
}

async function saveOnly() {
  if (!validateBeforeSave()) return;
  submitting.value = true;
  error.value = '';
  try {
    await postConfig();
    await loadUserLibrary();
    showTransientInfo('配置已保存到任务目录', 2500);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.response?.data?.message || err?.message || '保存失败';
  } finally {
    submitting.value = false;
  }
}

async function saveAsTemplate() {
  if (!validateBeforeSave()) return;
  const name = templateName.value.trim();
  if (!name) {
    error.value = '请填写模板名称';
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    await api.post('/user-config/templates', {
      name,
      config: buildCurrentConfig(),
    });
    templateName.value = '';
    saveTemplateOpen.value = false;
    await loadUserLibrary();
    showTransientInfo('已保存为我的模板');
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '保存模板失败';
  } finally {
    submitting.value = false;
  }
}

async function deleteTemplate(id: string) {
  if (readonly.value) return;
  try {
    await api.delete(`/user-config/templates/${encodeURIComponent(id)}`);
    await loadUserLibrary();
    showTransientInfo('模板已删除');
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '删除模板失败';
  }
}

function openSaveTemplate() {
  templateName.value = `${grade.value || '自定义'}${subject.value || '配置'}`;
  saveTemplateOpen.value = true;
}

function targetLabel(target: SuggestTarget): string {
  if (target === 'taxonomy') return '知识体系';
  if (target === 'ability_levels') return '核心素养';
  return '题型';
}

function itemTitle(item: unknown): string {
  if (!item || typeof item !== 'object') return '';
  return String((item as { name?: unknown }).name || '');
}

function itemDetail(item: unknown): string {
  if (!item || typeof item !== 'object') return '';
  const obj = item as Record<string, unknown>;
  if (Array.isArray(obj.subcategories)) return obj.subcategories.join('、');
  if (Array.isArray(obj.sublevels)) return obj.sublevels.join('、');
  if (obj.description) return String(obj.description);
  if (obj.weight !== undefined) {
    if (suggestTarget.value === 'question_types') {
      const share = questionTypeWeightFromStored(obj.weight);
      return `占比强度参考 ${share}（0–100）`;
    }
    return `权重 ${Number(obj.weight).toFixed(2)}`;
  }
  return '';
}

onMounted(async () => {
  await Promise.all([loadPresets(), loadUserLibrary()]);
  await loadExistingConfig();
});

onUnmounted(() => {
  if (infoDismissTimer) clearTimeout(infoDismissTimer);
});
</script>

<template>
  <div class="min-w-0">
    <div v-if="readonly" class="bg-amber-50 border border-amber-200 text-amber-700 rounded-xl p-3 text-sm mb-4">
      任务已 {{ taskStatus === 'running' ? '运行中' : '完成' }}，下方为只读视图，配置无法再次写入。
    </div>

    <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-6">
      <div class="flex items-center justify-between mb-5 gap-3 flex-wrap">
        <div class="flex items-center gap-2 sm:gap-3 flex-wrap">
          <template v-for="i in totalSteps" :key="i">
            <button
              type="button"
              :class="[
                'w-8 h-8 shrink-0 rounded-full text-sm font-medium grid place-items-center transition',
                i === step ? 'bg-slate-900 text-white' : i < step ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-500',
              ]"
              @click="step = i"
            >
              {{ i }}
            </button>
            <span v-if="i < totalSteps" class="h-px w-3 sm:w-6" :class="i < step ? 'bg-emerald-500' : 'bg-slate-200'" />
          </template>
        </div>
      </div>

      <p v-if="error" class="text-sm text-rose-600 mb-3">{{ error }}</p>

      <section v-if="step === 1" class="space-y-6">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">第 1 步 · 选择或创建配置</h2>
        </div>

        <div v-if="presetsLoading" class="text-sm text-slate-500">正在加载官方预设...</div>
        <template v-else>
          <div>
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-semibold text-slate-900">官方高中预设</h3>
              <span class="text-xs text-slate-400">{{ seniorPresets.length }} 个</span>
            </div>
            <div class="grid grid-cols-[repeat(auto-fit,minmax(8rem,1fr))] sm:grid-cols-3 gap-x-3 gap-y-3 justify-items-stretch">
              <button
                v-for="p in seniorPresets"
                :key="p"
                type="button"
                :class="[
                  'dfedu-config-preset-btn box-border w-full min-w-0 flex items-center justify-center border rounded-lg px-2 py-2 text-center transition',
                  selectedPreset === p && sourceType === 'official_preset'
                    ? 'border-slate-900 bg-slate-50 shadow-sm'
                    : 'border-slate-200 hover:border-slate-400 hover:bg-slate-50/60',
                ]"
                :disabled="readonly || presetLoading"
                @click="applyPreset(p)"
              >
                <div class="flex w-full flex-row items-center justify-center gap-2 min-w-0">
                  <span :class="presetSubjectBadgeLogoClass(p, selectedPreset === p && sourceType === 'official_preset')" aria-hidden="true">{{
                    presetSubjectBadgeChar(p)
                  }}</span>
                  <span
                    class="font-semibold text-slate-900 text-sm leading-snug text-center min-w-0 break-words"
                    >{{ presetLabel(p) }}</span>
                </div>
              </button>
            </div>
          </div>

          <div>
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-semibold text-slate-900">官方初中预设</h3>
              <span class="text-xs text-slate-400">{{ juniorPresets.length }} 个</span>
            </div>
            <div class="grid grid-cols-[repeat(auto-fit,minmax(8rem,1fr))] sm:grid-cols-3 gap-x-3 gap-y-3 justify-items-stretch">
              <button
                v-for="p in juniorPresets"
                :key="p"
                type="button"
                :class="[
                  'dfedu-config-preset-btn box-border w-full min-w-0 flex items-center justify-center border rounded-lg px-2 py-2 text-center transition',
                  selectedPreset === p && sourceType === 'official_preset'
                    ? 'border-slate-900 bg-slate-50 shadow-sm'
                    : 'border-slate-200 hover:border-slate-400 hover:bg-slate-50/60',
                ]"
                :disabled="readonly || presetLoading"
                @click="applyPreset(p)"
              >
                <div class="flex w-full flex-row items-center justify-center gap-2 min-w-0">
                  <span :class="presetSubjectBadgeLogoClass(p, selectedPreset === p && sourceType === 'official_preset')" aria-hidden="true">{{
                    presetSubjectBadgeChar(p)
                  }}</span>
                  <span
                    class="font-semibold text-slate-900 text-sm leading-snug text-center min-w-0 break-words"
                    >{{ presetLabel(p) }}</span>
                </div>
              </button>
            </div>
          </div>
        </template>

        <div class="space-y-4">
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h3 class="text-sm font-semibold text-slate-900">我的配置</h3>
              <p class="text-xs text-slate-500 mt-0.5">复用个人模板、最近使用，或从零开始创建自定义学段学科。</p>
            </div>
          </div>

          <button
            type="button"
            :class="[
              'w-full rounded-xl border p-4 text-left transition disabled:opacity-60',
              sourceType === 'custom'
                ? 'border-slate-900 bg-slate-50 shadow-sm ring-1 ring-slate-900/10'
                : 'border-dashed border-slate-300 bg-white hover:border-slate-500 hover:bg-slate-50',
            ]"
            :disabled="readonly"
            @click="createCustom"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-slate-900">自定义配置</p>
                <p class="text-xs text-slate-500 mt-1">
                  不使用官方预设，知识体系、核心素养从空白开始，题型和难度使用默认初始值。
                </p>
              </div>
              <span
                :class="[
                  'shrink-0 rounded-full px-2.5 py-1 text-xs font-medium',
                  sourceType === 'custom'
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600',
                ]"
              >
                {{ sourceType === 'custom' ? '当前选中' : '选择' }}
              </span>
            </div>
          </button>

          <div v-if="libraryLoading" class="text-sm text-slate-500">正在加载我的配置...</div>
          <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="border border-slate-200 rounded-xl p-4">
              <div class="flex items-center justify-between mb-3">
                <h4 class="text-sm font-medium text-slate-800">我的模板</h4>
                <span class="text-xs text-slate-400">{{ templates.length }} 个</span>
              </div>
              <div v-if="templates.length" class="space-y-2">
                <div
                  v-for="item in templates"
                  :key="item.id"
                  class="border border-slate-200 rounded-lg p-3 flex items-start justify-between gap-3"
                >
                  <button type="button" class="text-left min-w-0 flex-1" :disabled="readonly" @click="applySaved(item, 'user_template')">
                    <span class="block text-sm font-medium text-slate-900 truncate">{{ item.name }}</span>
                    <span class="block text-xs text-slate-500 mt-0.5 truncate">
                      {{ item.config.grade || '未填学段' }} · {{ item.config.subject || '未填学科' }}
                    </span>
                  </button>
                  <button
                    v-if="!readonly"
                    type="button"
                    class="text-xs text-rose-600 hover:underline flex-shrink-0"
                    @click="deleteTemplate(item.id)"
                  >
                    删除
                  </button>
                </div>
              </div>
              <p v-else class="text-sm text-slate-500">暂无模板，可在编辑区底部保存当前配置。</p>
            </div>

            <div class="border border-slate-200 rounded-xl p-4">
              <div class="flex items-center justify-between mb-3">
                <h4 class="text-sm font-medium text-slate-800">最近使用</h4>
                <span class="text-xs text-slate-400">最多 5 条</span>
              </div>
              <div v-if="recents.length" class="space-y-2">
                <button
                  v-for="item in recents"
                  :key="item.id"
                  type="button"
                  class="w-full border border-slate-200 rounded-lg p-3 text-left hover:border-slate-400 disabled:opacity-60"
                  :disabled="readonly"
                  @click="applySaved(item, 'recent')"
                >
                  <span class="block text-sm font-medium text-slate-900 truncate">{{ item.name }}</span>
                  <span class="block text-xs text-slate-500 mt-0.5 truncate">
                    {{ item.config.grade || '未填学段' }} · {{ item.config.subject || '未填学科' }}
                  </span>
                </button>
              </div>
              <p v-else class="text-sm text-slate-500">暂无最近使用记录。</p>
            </div>
          </div>
        </div>

        <div class="pt-6 mt-1 border-t border-slate-200">
          <div
            class="rounded-xl border border-slate-300 bg-white shadow-sm shadow-slate-900/5 ring-1 ring-slate-950/5 overflow-hidden"
            role="region"
            aria-label="当前编辑配置"
          >
            <div
              class="flex items-center justify-between gap-3 flex-wrap px-4 py-3 bg-slate-100/95 border-b border-slate-200"
            >
              <div class="min-w-0">
                <p class="text-sm font-semibold text-slate-900 tracking-tight">当前编辑配置</p>
                <p class="text-xs text-slate-600 mt-0.5">{{ selectedSourceSummary }}</p>
              </div>
              <span
                class="text-xs px-2.5 py-1 rounded-full bg-white border border-slate-200/90 text-slate-600 font-medium shadow-sm shrink-0"
              >
                {{ sourceType === 'official_preset' ? '官方预设副本' : sourceType === 'user_template' ? '我的模板副本' : sourceType === 'recent' ? '最近使用副本' : '自定义' }}
              </span>
            </div>
            <div class="p-4 sm:p-5 bg-slate-50/40">
              <div class="grid sm:grid-cols-2 gap-3">
                <label class="block">
                  <span class="text-xs text-slate-600 mb-1 block">学段</span>
                  <input
                    v-model="grade"
                    type="text"
                    placeholder="例如：高中、初中、大学本科"
                    class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900/20"
                    :disabled="readonly"
                  />
                </label>
                <label class="block">
                  <span class="text-xs text-slate-600 mb-1 block">学科</span>
                  <input
                    v-model="subject"
                    type="text"
                    placeholder="例如：生物学、网络与信息法学"
                    class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900/20"
                    :disabled="readonly"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="step === 2">
        <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-1">
          <h2 class="text-lg font-semibold text-slate-900">第 2 步 · 学科知识体系</h2>
          <button
            v-if="!readonly"
            type="button"
            class="w-full sm:w-auto text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:border-slate-900 hover:bg-slate-50"
            @click="openSuggest('taxonomy')"
          >
            联网生成知识体系建议
          </button>
        </div>
        <p class="text-sm text-slate-500 mb-4">
          学科知识体系用于约束题目考察范围，避免超纲。<br />
          除非您有特殊需求，否则不建议频繁修改学科知识体系。
        </p>
        <div class="space-y-3">
          <div v-for="(t, i) in taxonomy" :key="i" class="border border-slate-200 rounded-xl p-3">
            <div class="flex flex-col sm:flex-row sm:items-center gap-3">
              <input v-model="t.name" type="text" class="flex-1 px-2 py-1 border border-slate-300 rounded-lg text-sm font-medium" :disabled="readonly" />
              <button v-if="!readonly" class="text-xs text-rose-600 hover:underline" @click="removeTaxonomy(i)">删除</button>
            </div>
            <div class="mt-2 space-y-2">
              <div class="flex flex-wrap gap-2">
                <span v-for="(_, j) in t.subcategories" :key="j" class="inline-flex w-fit max-w-full shrink-0 items-center gap-1 px-2 py-1 rounded-lg bg-slate-100 text-xs text-slate-700">
                  <input
                    v-model="t.subcategories[j]"
                    type="text"
                    class="min-w-[3ch] max-w-full bg-transparent focus:outline-none [field-sizing:content]"
                    :disabled="readonly"
                  />
                  <button v-if="!readonly" type="button" class="shrink-0 text-slate-400 hover:text-rose-500" @click="removeSubcategory(t, j)">×</button>
                </span>
              </div>
              <button v-if="!readonly" type="button" class="text-xs text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-lg px-2 py-1" @click="addSubcategory(t)">
                + 小类
              </button>
            </div>
          </div>
          <button v-if="!readonly" class="text-sm text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-xl px-3 py-2 w-full" @click="addTaxonomy">+ 添加知识大类</button>
          <p v-if="!taxonomy.length" class="text-sm text-slate-500">尚无知识体系，可手动添加或通过联网建议生成。</p>
        </div>
      </section>

      <section v-else-if="step === 3">
        <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-1">
          <h2 class="text-lg font-semibold text-slate-900">第 3 步 · 学科核心素养</h2>
          <button
            v-if="!readonly"
            type="button"
            class="w-full sm:w-auto text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:border-slate-900 hover:bg-slate-50"
            @click="openSuggest('ability_levels')"
          >
            联网生成核心素养建议
          </button>
        </div>
        <p class="text-sm text-slate-500 mb-4">
          学科核心素养用于约束题目考察范围，避免超纲。<br />
          除非您有特殊需求，否则不建议频繁修改学科核心素养。
        </p>
        <div class="space-y-3">
          <div v-for="(a, i) in abilityLevels" :key="i" class="border border-slate-200 rounded-xl p-3">
            <div class="flex items-center gap-3 flex-wrap">
              <input v-model="a.name" type="text" class="flex-1 min-w-[8rem] px-2 py-1 border border-slate-300 rounded-lg text-sm font-medium" :disabled="readonly" />
              <label class="flex items-center gap-2 text-xs text-slate-500">
                权重
                <input v-model.number="a.weight" type="number" step="0.05" min="0" max="1" class="w-20 px-2 py-1 border border-slate-300 rounded-lg" :disabled="readonly" />
              </label>
              <button v-if="!readonly" class="text-xs text-rose-600 hover:underline" @click="removeAbility(i)">删除</button>
            </div>
            <input v-model="a.description" type="text" class="mt-2 w-full px-2 py-1 border border-slate-200 rounded-lg text-xs text-slate-600" placeholder="描述（可选）" :disabled="readonly" />
            <div class="mt-2 flex flex-wrap gap-1.5">
              <span v-for="(s, j) in a.sublevels" :key="j" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-700">
                {{ s }}
                <button v-if="!readonly" class="text-slate-400 hover:text-rose-500" @click="removeSublevel(a, j)">×</button>
              </span>
              <button v-if="!readonly" class="text-xs text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-full px-2" @click="addSublevel(a)">+ 子层级</button>
            </div>
          </div>
          <button v-if="!readonly" class="text-sm text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-xl px-3 py-2 w-full" @click="addAbility">+ 添加核心素养</button>
          <p v-if="!abilityLevels.length" class="text-sm text-slate-500">尚无核心素养，可手动添加或通过联网建议生成。</p>
        </div>
      </section>

      <section v-else-if="step === 4">
        <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-1">
          <h2 class="text-lg font-semibold text-slate-900">第 4 步 · 设置题型分布</h2>
          <button
            v-if="!readonly"
            type="button"
            class="w-full sm:w-auto text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:border-slate-900 hover:bg-slate-50"
            @click="openSuggest('question_types')"
          >
            联网生成题型建议
          </button>
        </div>
        <p class="text-sm text-slate-500 mb-4">您可以任意调整您想要的题型种类与分布占比。</p>
        <p v-if="!readonly && questionTypes.length && sumQuestionTypes <= 0" class="text-sm text-rose-600 mb-3">
          请至少拉高一种题型的占比强度，否则无法进入下一步。
        </p>
        <div v-if="qtBars.length" class="flex h-3 w-full rounded-full overflow-hidden bg-slate-100 mb-4">
          <div v-for="(b, i) in qtBars" :key="i" :class="b.color" :style="{ width: b.pct + '%' }" :title="`${b.name} ${b.pct.toFixed(1)}%`" />
        </div>
        <div class="space-y-2">
          <div v-for="(q, i) in questionTypes" :key="i" class="flex flex-col sm:flex-row sm:items-center gap-3 border border-slate-200 rounded-xl p-3">
            <span class="inline-block w-3 h-3 rounded-full" :class="presetColors[i % presetColors.length]" />
            <input v-model="q.name" type="text" class="w-full sm:flex-1 sm:min-w-[8rem] px-2 py-1 border border-slate-300 rounded-lg text-sm" :disabled="readonly" />
            <input
              v-model.number="q.weight"
              type="range"
              min="0"
              max="100"
              step="1"
              class="w-full sm:flex-1 sm:min-w-[6rem] accent-slate-900"
              :disabled="readonly"
              @input="clampQtPercentStrength(q)"
              @change="clampQtPercentStrength(q)"
            />
            <span class="w-full sm:w-14 text-xs text-slate-500 text-left sm:text-right tabular-nums" :title="sumQuestionTypes > 0 ? `约生成占比 ${((Number(q.weight) || 0) / sumQuestionTypes * 100).toFixed(1)}%` : '无有效占比'">
              {{ sumQuestionTypes > 0 ? ((Number(q.weight) || 0) / sumQuestionTypes * 100).toFixed(0) : '—' }}%
            </span>
            <button v-if="!readonly" class="text-xs text-rose-600 hover:underline" @click="removeQT(i)">删除</button>
          </div>
          <button v-if="!readonly" class="text-sm text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-xl px-3 py-2 w-full" @click="addQT">+ 添加题型</button>
          <p v-if="!questionTypes.length" class="text-sm text-slate-500">尚无题型，可手动添加或通过联网建议生成。</p>
        </div>
      </section>

      <section v-else-if="step === 5">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 5 步 · 难度分布</h2>
        <p class="text-sm text-slate-500 mb-4">您可以任意调整题目难度分布，难度分为易/中/难三级。</p>
        <div class="flex h-3 w-full rounded-full overflow-hidden bg-slate-100 mb-4">
          <div class="bg-emerald-300" :style="{ width: ((difficulty.easy / (sumDifficulty || 1)) * 100) + '%' }" />
          <div class="bg-amber-300" :style="{ width: ((difficulty.medium / (sumDifficulty || 1)) * 100) + '%' }" />
          <div class="bg-rose-300" :style="{ width: ((difficulty.hard / (sumDifficulty || 1)) * 100) + '%' }" />
        </div>
        <p v-if="!readonly && sumDifficulty <= 0" class="text-sm text-rose-600 mb-3">
          请至少调高一档难度的占比强度，否则无法进入下一步。
        </p>
        <div class="space-y-4">
          <div v-for="key in (['easy', 'medium', 'hard'] as const)" :key="key" class="flex items-center gap-3">
            <span class="w-12 text-sm text-slate-700">{{ key === 'easy' ? '易' : key === 'medium' ? '中' : '难' }}</span>
            <input
              v-model.number="difficulty[key]"
              type="range"
              min="0"
              max="100"
              step="1"
              class="flex-1 min-w-[6rem] accent-slate-900"
              :disabled="readonly"
              @input="clampDifficultyStrength(key)"
              @change="clampDifficultyStrength(key)"
            />
            <span
              class="w-14 text-xs text-slate-500 text-right tabular-nums"
              :title="sumDifficulty > 0 ? `约生成占比 ${((Number(difficulty[key]) || 0) / sumDifficulty * 100).toFixed(1)}%` : '无有效占比'"
            >
              {{ sumDifficulty > 0 ? ((Number(difficulty[key]) || 0) / sumDifficulty * 100).toFixed(0) : '—' }}%
            </span>
          </div>
        </div>
      </section>

      <section v-else-if="step === 6">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 6 步 · 可选步骤</h2>
        <p class="text-sm text-slate-500 mb-4">
          建议选择除【3.7 多语言翻译】步骤以外的所有步骤，以保证最佳出题质量<br />【3.1与3.2为绑定步骤，同开同关】【3.3与3.4为绑定步骤，同开同关】<br />未选中的步骤将直接被跳过
        </p>
        <ol class="relative" aria-label="可选流水线时间线">
          <li
            v-for="(s, idx) in OPTIONAL_STAGES"
            :key="s.name"
            class="relative grid grid-cols-[2.25rem_minmax(0,1fr)] items-stretch gap-3 pb-3 last:pb-0"
          >
            <div class="relative flex self-stretch items-center justify-center">
              <div
                v-if="idx > 0"
                :class="[
                  'absolute left-1/2 top-[-0.75rem] bottom-1/2 w-px -translate-x-1/2',
                  enabledStages.has(OPTIONAL_STAGES[idx - 1].name) ? 'bg-slate-900' : 'bg-slate-200',
                ]"
              />
              <button
                type="button"
                :disabled="readonly"
                :aria-pressed="enabledStages.has(s.name)"
                :aria-label="
                  readonly
                    ? `${s.name}，任务锁定不可修改`
                    : enabledStages.has(s.name)
                      ? `${s.name}，已启用，点击跳过`
                      : `${s.name}，已跳过，点击启用`
                "
                :title="readonly ? '任务运行中或已完成，不能修改步骤' : enabledStages.has(s.name) ? '点击跳过此步骤' : '点击启用此步骤'"
                :class="[
                  'relative z-10 flex h-9 w-9 items-center justify-center rounded-full border-2 text-xs font-semibold tabular-nums transition',
                  readonly ? 'cursor-default' : 'cursor-pointer hover:scale-105',
                  enabledStages.has(s.name)
                    ? 'border-slate-900 bg-slate-900 text-white shadow-sm'
                    : 'border-slate-300 bg-white text-slate-500',
                ]"
                @click="toggleStage(s)"
              >
                <svg v-if="enabledStages.has(s.name)" class="h-4 w-4" viewBox="0 0 12 12" fill="none">
                  <path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span v-else class="text-[10px] font-semibold leading-none">跳过</span>
              </button>
              <div
                v-if="idx < OPTIONAL_STAGES.length - 1"
                :class="[
                  'absolute left-1/2 top-1/2 bottom-[-0.75rem] w-px -translate-x-1/2',
                  enabledStages.has(s.name) ? 'bg-slate-900' : 'bg-slate-200',
                ]"
              />
            </div>

            <button
              type="button"
              :disabled="readonly"
              :aria-pressed="enabledStages.has(s.name)"
              :class="[
                'w-full rounded-xl border p-4 text-left transition',
                readonly ? 'cursor-default' : 'cursor-pointer',
                enabledStages.has(s.name)
                  ? 'border-slate-900 bg-slate-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-400',
              ]"
              @click="toggleStage(s)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
                    <p class="text-sm font-medium text-slate-900 leading-snug break-words">{{ s.name }}</p>
                    <p v-if="s.pairName" class="text-xs text-amber-600 leading-snug">
                      与「{{ s.pairName }}」绑定
                    </p>
                  </div>
                  <p class="text-xs text-slate-500 mt-1 leading-snug">{{ s.desc }}</p>
                </div>
                <span
                  :class="[
                    'shrink-0 rounded-full px-2.5 py-1 text-xs font-medium',
                    enabledStages.has(s.name) ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-500',
                  ]"
                >
                  {{ enabledStages.has(s.name) ? '执行' : '跳过' }}
                </span>
              </div>
            </button>
          </li>
        </ol>
      </section>

      <div
        v-if="showCustomTemplatePrompt"
        class="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"
      >
        <div class="flex items-start justify-between gap-3 flex-wrap">
          <div class="min-w-0">
            <p class="text-sm font-medium text-amber-900">当前选择的是自定义配置</p>
            <p class="text-xs text-amber-700 mt-1">是否要保存这个配置，方便之后在「我的模板」中复用？</p>
          </div>
          <div class="flex items-center gap-2 flex-wrap justify-end w-full sm:w-auto">
            <template v-if="saveTemplateOpen">
              <input
                v-model="templateName"
                type="text"
                class="w-full sm:w-44 px-3 py-2 border border-amber-300 rounded-lg text-sm bg-white"
                placeholder="模板名称"
              />
              <button
                class="px-3 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
                :disabled="submitting"
                @click="saveAsTemplate"
              >
                确认保存
              </button>
            </template>
            <button
              v-else
              class="px-3 py-2 text-sm border border-amber-300 bg-white rounded-lg text-amber-800 hover:border-amber-500 disabled:opacity-50"
              :disabled="submitting"
              @click="openSaveTemplate"
            >
              保存为我的模板
            </button>
          </div>
        </div>
      </div>

      <div
        v-if="suggestOpen"
        class="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4"
        @click.self="closeSuggest"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
          <div class="px-4 sm:px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-3">
            <div class="min-w-0">
              <h3 class="text-base font-semibold text-slate-900">联网生成{{ targetLabel(suggestTarget) }}</h3>
              <p class="text-xs text-slate-500 mt-0.5 truncate">学段：{{ grade || '(未填写)' }} · 学科：{{ subject || '(未填写)' }} · 教材：{{ taskName || '(无)' }}</p>
            </div>
            <button class="text-slate-400 hover:text-slate-700 text-xl leading-none" @click="closeSuggest" aria-label="close">×</button>
          </div>
          <div class="px-4 sm:px-5 py-4 space-y-3 overflow-auto">
            <label class="block">
              <span class="text-xs text-slate-600 mb-1 block">个性化需求（可选，{{ suggestNeeds.length }}/{{ NEEDS_MAX }}）</span>
              <textarea v-model="suggestNeeds" :maxlength="NEEDS_MAX" rows="3" placeholder="例如：希望更贴近实验探究和跨学科应用" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-slate-900" />
            </label>
            <div class="flex flex-col sm:flex-row sm:items-center gap-2">
              <button class="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50" :disabled="suggestLoading" @click="fetchSuggest">
                {{ suggestLoading ? '生成中...' : '开始生成' }}
              </button>
              <span v-if="suggestState.source === 'live'" class="text-xs text-slate-500">来自联网检索</span>
            </div>
            <p v-if="suggestError" class="text-sm text-rose-600">{{ suggestError }}</p>
            <div v-if="suggestItems.length" class="space-y-2">
              <p class="text-xs text-slate-500">共 {{ suggestItems.length }} 条建议，应用前请确认。</p>
              <div v-for="(it, i) in suggestItems" :key="i" class="border border-slate-200 rounded-xl p-3">
                <p class="text-sm font-medium text-slate-900">{{ itemTitle(it) }}</p>
                <p v-if="itemDetail(it)" class="text-xs text-slate-600 mt-1">{{ itemDetail(it) }}</p>
              </div>
            </div>
          </div>
          <div class="px-4 sm:px-5 py-3 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2">
            <button class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900" @click="closeSuggest">取消</button>
            <button class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50" :disabled="!suggestItems.length" @click="applySuggestions('merge')">合并到当前配置</button>
            <button class="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50" :disabled="!suggestItems.length" @click="applySuggestions('replace')">替换当前步骤</button>
          </div>
        </div>
      </div>

      <div class="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-2 flex-wrap">
        <button
          class="w-full sm:w-auto px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900 disabled:opacity-50"
          :disabled="step === 1"
          @click="prev"
        >
          ← 上一步
        </button>
        <div class="flex flex-col sm:flex-row sm:items-center gap-2 flex-wrap sm:justify-end w-full sm:w-auto">
          <button
            v-if="!readonly && step === totalSteps"
            class="px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900 disabled:opacity-50"
            :disabled="submitting"
            @click="saveOnly"
          >
            仅保存配置
          </button>
          <button
            v-if="step < totalSteps"
            class="px-4 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
            :disabled="!canNext"
            @click="next"
          >
            下一步 →
          </button>
          <button
            v-else-if="!readonly"
            class="px-4 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
            :disabled="submitting"
            @click="saveAndRun"
          >
            {{ submitting ? '提交中...' : '保存配置并开始生成习题' }}
          </button>
          <button v-else class="px-4 py-2 text-sm bg-slate-300 text-white rounded-lg cursor-not-allowed" disabled>
            任务已启动，无法再次开始
          </button>
        </div>
      </div>
    </div>

    <Transition name="dfedu-toast">
      <div
        v-if="info"
        class="dfedu-toast-panel fixed bottom-6 right-4 sm:right-6 z-[100] max-w-[min(16.8rem,calc(100vw-2rem))] rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-900 shadow-lg shadow-slate-900/10 pointer-events-none will-change-transform"
        role="status"
        aria-live="polite"
      >
        {{ info }}
      </div>
    </Transition>
  </div>
</template>

<style>
.dfedu-config-preset-btn {
  box-sizing: border-box;
  height: 4.25rem;
  min-height: 4.25rem;
  align-self: center;
}

.dfedu-toast-enter-active,
.dfedu-toast-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}
.dfedu-toast-enter-from,
.dfedu-toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
