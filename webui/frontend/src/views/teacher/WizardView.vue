<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '@/api/client';

const props = defineProps<{
  id: string;
  taskStatus?: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  taskName?: string;
}>();

const router = useRouter();
const COMPETENCY_CACHE_KEY = 'edu_competency_suggest_cache_v1';

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

const presets = ref<string[]>([]);
const presetsLoading = ref(false);
const selectedPreset = ref('');
const taxonomy = ref<TaxonomyItem[]>([]);
const abilityLevels = ref<AbilityLevel[]>([]);
const questionTypes = ref<QuestionType[]>([]);
const difficulty = ref<DifficultyDist>({ easy: 0.3, medium: 0.5, hard: 0.2 });

const step = ref(1);
const error = ref('');
const info = ref('');
const submitting = ref(false);
const presetLoading = ref(false);
const existingLoaded = ref(false);

const readonly = computed(() => {
  return props.taskStatus === 'running' || props.taskStatus === 'succeeded';
});

const totalSteps = 4;

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

async function applyPreset(name: string) {
  if (!name) return;
  presetLoading.value = true;
  try {
    const { data } = await api.get(`/config/presets/${encodeURIComponent(name)}`);
    taxonomy.value = Array.isArray(data?.taxonomy) ? data.taxonomy : [];
    abilityLevels.value = Array.isArray(data?.ability_levels)
      ? data.ability_levels.map((a: any) => ({
          name: String(a.name || ''),
          weight: Number(a.weight ?? 0.25),
          description: String(a.description || ''),
          sublevels: Array.isArray(a.sublevels) ? a.sublevels.map(String) : [],
        }))
      : [];
    questionTypes.value = Array.isArray(data?.question_types)
      ? data.question_types.map((q: any) => ({
          name: String(q.name || ''),
          weight: Number(q.weight ?? 0.25),
        }))
      : [];
    if (data?.difficulty_distribution) {
      difficulty.value = {
        easy: Number(data.difficulty_distribution.easy ?? 0.3),
        medium: Number(data.difficulty_distribution.medium ?? 0.5),
        hard: Number(data.difficulty_distribution.hard ?? 0.2),
      };
    }
    selectedPreset.value = name;
    info.value = `已加载 ${name} 预设默认值，可继续微调或跳过余下步骤`;
    setTimeout(() => (info.value = ''), 3000);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载预设失败';
  } finally {
    presetLoading.value = false;
  }
}

async function loadExistingConfig() {
  try {
    const { data } = await api.get(`/tasks/${props.id}/config`);
    if (data?.exists && data.config) {
      const cfg = data.config;
      if (Array.isArray(cfg.taxonomy)) taxonomy.value = cfg.taxonomy;
      if (Array.isArray(cfg.ability_levels)) {
        abilityLevels.value = cfg.ability_levels.map((a: any) => ({
          name: String(a.name || ''),
          weight: Number(a.weight ?? 0.25),
          description: String(a.description || ''),
          sublevels: Array.isArray(a.sublevels) ? a.sublevels.map(String) : [],
        }));
      }
      if (Array.isArray(cfg.question_types)) {
        questionTypes.value = cfg.question_types.map((q: any) => ({
          name: String(q.name || ''),
          weight: Number(q.weight ?? 0.25),
        }));
      }
      if (cfg.difficulty_distribution) {
        difficulty.value = {
          easy: Number(cfg.difficulty_distribution.easy ?? 0.3),
          medium: Number(cfg.difficulty_distribution.medium ?? 0.5),
          hard: Number(cfg.difficulty_distribution.hard ?? 0.2),
        };
      }
      existingLoaded.value = true;
    }
  } catch {
    // ignore
  }
}

const sumQuestionTypes = computed(() =>
  questionTypes.value.reduce((s, q) => s + (Number(q.weight) || 0), 0),
);

const sumAbility = computed(() =>
  abilityLevels.value.reduce((s, a) => s + (Number(a.weight) || 0), 0),
);

const sumDifficulty = computed(
  () =>
    (Number(difficulty.value.easy) || 0) +
    (Number(difficulty.value.medium) || 0) +
    (Number(difficulty.value.hard) || 0),
);

const canNext = computed(() => {
  if (step.value === 1) return !!selectedPreset.value && !presetLoading.value;
  return true;
});

function next() {
  if (step.value < totalSteps) step.value += 1;
}
function prev() {
  if (step.value > 1) step.value -= 1;
}
function skip() {
  next();
}

function removeAbility(idx: number) {
  abilityLevels.value.splice(idx, 1);
}

// ============== 联网素养建议 ==============
interface SuggestItem {
  name: string;
  dimension?: string;
  description?: string;
  source_url?: string;
  _checked?: boolean;
}

const suggestOpen = ref(false);
const suggestNeeds = ref('');
const suggestLoading = ref(false);
const suggestError = ref('');
const suggestItems = ref<SuggestItem[]>([]);
const NEEDS_MAX = 500;
const suggestState = reactive({ source: '' as 'cache' | 'live' | '' });

function suggestCacheKey(subject: string, book: string, needs: string): string {
  // 简易 cache key：subject|book|trim+lower(needs)，避免引入额外依赖
  return [subject, book, needs.replace(/\s+/g, ' ').trim().toLowerCase()].join('||');
}

function readSuggestCache(key: string): SuggestItem[] | null {
  try {
    const raw = localStorage.getItem(COMPETENCY_CACHE_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw) as Record<string, { items: SuggestItem[]; ts: number }>;
    const hit = obj[key];
    if (!hit || !Array.isArray(hit.items)) return null;
    // 24h TTL
    if (Date.now() - hit.ts > 24 * 60 * 60 * 1000) return null;
    return hit.items;
  } catch {
    return null;
  }
}

function writeSuggestCache(key: string, items: SuggestItem[]) {
  try {
    const raw = localStorage.getItem(COMPETENCY_CACHE_KEY);
    const obj = raw ? (JSON.parse(raw) as Record<string, { items: SuggestItem[]; ts: number }>) : {};
    obj[key] = { items, ts: Date.now() };
    // 限制最多保留 16 条
    const keys = Object.keys(obj);
    if (keys.length > 16) {
      keys
        .map((k) => ({ k, ts: obj[k].ts }))
        .sort((a, b) => a.ts - b.ts)
        .slice(0, keys.length - 16)
        .forEach((it) => delete obj[it.k]);
    }
    localStorage.setItem(COMPETENCY_CACHE_KEY, JSON.stringify(obj));
  } catch {
    /* ignore quota errors */
  }
}

function openSuggest() {
  if (!selectedPreset.value) {
    error.value = '请先在第 1 步选择学科';
    step.value = 1;
    return;
  }
  suggestOpen.value = true;
  suggestError.value = '';
  suggestItems.value = [];
  suggestState.source = '';
  suggestNeeds.value = '';
}

function closeSuggest() {
  suggestOpen.value = false;
  suggestLoading.value = false;
}

async function fetchSuggest() {
  suggestError.value = '';
  if (!props.taskName) {
    suggestError.value = '当前任务缺少教材名，无法发起检索';
    return;
  }
  if (suggestNeeds.value.length > NEEDS_MAX) {
    suggestError.value = `个性化需求最长 ${NEEDS_MAX} 字`;
    return;
  }
  const subject = selectedPreset.value;
  const book = props.taskName;
  const needs = suggestNeeds.value.trim();
  const key = suggestCacheKey(subject, book, needs);
  const cached = readSuggestCache(key);
  if (cached && cached.length) {
    suggestItems.value = cached.map((it) => ({ ...it, _checked: true }));
    suggestState.source = 'cache';
    return;
  }
  suggestLoading.value = true;
  try {
    const { data } = await api.post('/competency/suggest', {
      subject,
      book,
      needs,
    });
    const items = Array.isArray(data?.competencies) ? (data.competencies as SuggestItem[]) : [];
    if (!items.length) {
      suggestError.value = '联网模型未返回有效建议，请稍后重试或缩短个性化需求';
      return;
    }
    suggestItems.value = items.map((it) => ({ ...it, _checked: true }));
    suggestState.source = 'live';
    writeSuggestCache(key, items);
  } catch (err: any) {
    const code = err?.response?.data?.error;
    const msg = err?.response?.data?.message;
    if (code === 'missing_llm_key') {
      suggestError.value = '本地未保存 LLM Key，请回到「新建任务」页填写后重试';
    } else if (code === 'rate_limited') {
      suggestError.value = msg || '调用过于频繁，请稍后再试';
    } else if (code === 'needs_too_long') {
      suggestError.value = msg || `个性化需求最长 ${NEEDS_MAX} 字`;
    } else if (err?.response?.status === 504) {
      suggestError.value = '联网 LLM 调用超时（30s），请稍后再试';
    } else {
      suggestError.value = msg || code || err?.message || '联网建议失败';
    }
  } finally {
    suggestLoading.value = false;
  }
}

function applySelectedSuggestions() {
  const picked = suggestItems.value.filter((it) => it._checked);
  if (!picked.length) {
    closeSuggest();
    return;
  }
  // 合并策略：按 dimension 聚合到 abilityLevels；同 dimension 已存在则把 name 加到 sublevels（去重）
  const dimMap = new Map<string, AbilityLevel>();
  for (const lv of abilityLevels.value) {
    if (lv.name) dimMap.set(lv.name, lv);
  }
  for (const it of picked) {
    const dim = (it.dimension || '其它素养').trim();
    const subName = (it.name || '').trim();
    if (!subName) continue;
    let target = dimMap.get(dim);
    if (!target) {
      target = {
        name: dim,
        weight: 0.25,
        description: it.description || '',
        sublevels: [],
      };
      abilityLevels.value.push(target);
      dimMap.set(dim, target);
    }
    const subs = target.sublevels || (target.sublevels = []);
    if (!subs.includes(subName)) subs.push(subName);
    if (!target.description && it.description) {
      target.description = it.description;
    }
  }
  info.value = `已合并 ${picked.length} 条联网素养建议`;
  setTimeout(() => (info.value = ''), 3000);
  closeSuggest();
}
function removeQT(idx: number) {
  questionTypes.value.splice(idx, 1);
}
function addQT() {
  questionTypes.value.push({ name: '新题型', weight: 0.1 });
}
function removeSublevel(level: AbilityLevel, idx: number) {
  level.sublevels = (level.sublevels || []).filter((_, i) => i !== idx);
}

const presetColors = ['bg-rose-300', 'bg-amber-300', 'bg-emerald-300', 'bg-sky-300', 'bg-purple-300', 'bg-pink-300', 'bg-orange-300'];

const qtBars = computed(() => {
  const total = sumQuestionTypes.value || 1;
  return questionTypes.value.map((q, i) => ({
    name: q.name,
    pct: ((Number(q.weight) || 0) / total) * 100,
    color: presetColors[i % presetColors.length],
  }));
});

async function saveAndRun() {
  if (!selectedPreset.value) {
    error.value = '请先在第 1 步选择学科';
    step.value = 1;
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    await api.post(`/tasks/${props.id}/config`, {
      preset: selectedPreset.value,
      overrides: {
        taxonomy: taxonomy.value,
        ability_levels: abilityLevels.value,
        question_types: questionTypes.value,
        difficulty_distribution: difficulty.value,
      },
    });
    if (!readonly.value) {
      await api.post(`/tasks/${props.id}/run`);
    }
    router.replace(`/teacher/tasks/${props.id}`);
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'task_already_running') {
      error.value = '任务已在运行中';
    } else if (code === 'user_has_running_task') {
      error.value = '你已有任务在跑，等它结束后再启动新任务';
    } else if (code === 'missing_llm_key') {
      error.value = 'LLM Key 缺失，请先回到「新建任务」页填写以保存到本地';
    } else {
      error.value = err?.response?.data?.message || err?.message || '提交失败';
    }
  } finally {
    submitting.value = false;
  }
}

async function saveOnly() {
  if (!selectedPreset.value) {
    error.value = '请先在第 1 步选择学科';
    step.value = 1;
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    await api.post(`/tasks/${props.id}/config`, {
      preset: selectedPreset.value,
      overrides: {
        taxonomy: taxonomy.value,
        ability_levels: abilityLevels.value,
        question_types: questionTypes.value,
        difficulty_distribution: difficulty.value,
      },
    });
    info.value = '配置已保存到任务目录';
    setTimeout(() => (info.value = ''), 2500);
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.response?.data?.message || err?.message || '保存失败';
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  await loadPresets();
  await loadExistingConfig();
});
</script>

<template>
  <div>
    <div v-if="readonly" class="bg-amber-50 border border-amber-200 text-amber-700 rounded-xl p-3 text-sm mb-4">
      任务已 {{ taskStatus === 'running' ? '运行中' : '完成' }}，下方为只读视图，配置无法再次写入。
    </div>

    <div class="bg-white border border-slate-200 rounded-2xl p-6">
      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-3 flex-wrap">
          <template v-for="i in totalSteps" :key="i">
            <button
              type="button"
              :class="[
                'w-8 h-8 rounded-full text-sm font-medium grid place-items-center transition',
                i === step
                  ? 'bg-slate-900 text-white'
                  : i < step
                    ? 'bg-emerald-500 text-white'
                    : 'bg-slate-100 text-slate-500',
              ]"
              @click="step = i"
            >
              {{ i }}
            </button>
            <span
              v-if="i < totalSteps"
              class="h-px w-6"
              :class="i < step ? 'bg-emerald-500' : 'bg-slate-200'"
            />
          </template>
        </div>
        <button
          v-if="step < totalSteps && !readonly && step > 1"
          class="text-xs text-slate-500 hover:text-slate-900 underline"
          @click="skip"
        >
          跳过本步用 preset 默认 →
        </button>
      </div>

      <p v-if="error" class="text-sm text-rose-600 mb-3">{{ error }}</p>
      <p v-if="info" class="text-sm text-emerald-600 mb-3">{{ info }}</p>

      <!-- Step 1: Subject -->
      <section v-if="step === 1">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 1 步 · 选择学科</h2>
        <p class="text-sm text-slate-500 mb-4">
          学科决定了知识体系（taxonomy）与默认认知层级，是必选项。后续 3 步将以学科预设为起点。
        </p>
        <div v-if="presetsLoading" class="text-slate-500">加载中...</div>
        <div v-else-if="!presets.length" class="text-slate-500">
          暂无预设，请先去 <router-link to="/admin" class="text-slate-900 underline">管理员看板</router-link> 创建预设。
        </div>
        <div v-else class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <button
            v-for="p in presets"
            :key="p"
            type="button"
            :class="[
              'border rounded-xl p-4 text-left transition',
              selectedPreset === p
                ? 'border-slate-900 bg-slate-50'
                : 'border-slate-200 hover:border-slate-400',
            ]"
            :disabled="readonly || presetLoading"
            @click="applyPreset(p)"
          >
            <div class="font-medium text-slate-900">{{ p }}</div>
            <div class="text-xs text-slate-500 mt-1">
              {{ selectedPreset === p ? '✓ 已选用' : '点击选择' }}
            </div>
          </button>
        </div>
      </section>

      <!-- Step 2: Ability levels -->
      <section v-else-if="step === 2">
        <div class="flex items-start justify-between gap-3 mb-1">
          <h2 class="text-lg font-semibold text-slate-900">第 2 步 · 核心素养</h2>
          <button
            v-if="!readonly"
            type="button"
            class="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:border-slate-900 hover:bg-slate-50"
            title="联网检索权威课程标准，给当前学科 + 教材生成结构化素养候选"
            @click="openSuggest"
          >
            联网建议（找不到匹配）
          </button>
        </div>
        <p class="text-sm text-slate-500 mb-4">
          决定题目的认知层级分布。权重为相对值，无需必须等于 1（合计 {{ sumAbility.toFixed(2) }}）。
        </p>
        <div class="space-y-3">
          <div
            v-for="(a, i) in abilityLevels"
            :key="i"
            class="border border-slate-200 rounded-xl p-3"
          >
            <div class="flex items-center gap-3 flex-wrap">
              <input
                v-model="a.name"
                type="text"
                class="flex-1 min-w-[8rem] px-2 py-1 border border-slate-300 rounded-lg text-sm font-medium"
                :disabled="readonly"
              />
              <label class="flex items-center gap-2 text-xs text-slate-500">
                权重
                <input
                  v-model.number="a.weight"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  class="w-20 px-2 py-1 border border-slate-300 rounded-lg"
                  :disabled="readonly"
                />
              </label>
              <button
                v-if="!readonly"
                class="text-xs text-rose-600 hover:underline"
                @click="removeAbility(i)"
              >
                删除
              </button>
            </div>
            <input
              v-model="a.description"
              type="text"
              class="mt-2 w-full px-2 py-1 border border-slate-200 rounded-lg text-xs text-slate-600"
              placeholder="描述（可选）"
              :disabled="readonly"
            />
            <div v-if="a.sublevels?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="(s, j) in a.sublevels"
                :key="j"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-xs text-slate-700"
              >
                {{ s }}
                <button
                  v-if="!readonly"
                  class="text-slate-400 hover:text-rose-500"
                  @click="removeSublevel(a, j)"
                >
                  ×
                </button>
              </span>
            </div>
          </div>
          <div v-if="!abilityLevels.length" class="text-sm text-slate-500">尚无数据，请先在第 1 步选择学科以载入默认值</div>
        </div>
      </section>

      <!-- Step 3: Question types -->
      <section v-else-if="step === 3">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 3 步 · 题型</h2>
        <p class="text-sm text-slate-500 mb-4">
          各题型的相对权重决定生成比例。当前合计 {{ sumQuestionTypes.toFixed(2) }}。
        </p>
        <div v-if="qtBars.length" class="flex h-3 w-full rounded-full overflow-hidden bg-slate-100 mb-4">
          <div
            v-for="(b, i) in qtBars"
            :key="i"
            :class="b.color"
            :style="{ width: b.pct + '%' }"
            :title="`${b.name} ${b.pct.toFixed(1)}%`"
          />
        </div>
        <div class="space-y-2">
          <div
            v-for="(q, i) in questionTypes"
            :key="i"
            class="flex items-center gap-3 border border-slate-200 rounded-xl p-3"
          >
            <span class="inline-block w-3 h-3 rounded-full" :class="presetColors[i % presetColors.length]" />
            <input
              v-model="q.name"
              type="text"
              class="flex-1 min-w-[8rem] px-2 py-1 border border-slate-300 rounded-lg text-sm"
              :disabled="readonly"
            />
            <input
              v-model.number="q.weight"
              type="range"
              min="0"
              max="1"
              step="0.01"
              class="flex-1"
              :disabled="readonly"
            />
            <span class="w-12 text-xs text-slate-500 text-right">{{ (Number(q.weight) || 0).toFixed(2) }}</span>
            <button
              v-if="!readonly"
              class="text-xs text-rose-600 hover:underline"
              @click="removeQT(i)"
            >
              删除
            </button>
          </div>
          <button
            v-if="!readonly"
            class="text-sm text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-xl px-3 py-2 w-full"
            @click="addQT"
          >
            + 添加题型
          </button>
        </div>
      </section>

      <!-- Step 4: Difficulty -->
      <section v-else-if="step === 4">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 4 步 · 难度分布</h2>
        <p class="text-sm text-slate-500 mb-4">
          易/中/难三档比例（合计 {{ sumDifficulty.toFixed(2) }}），将作为题目难度的参考分布写入配置。
        </p>
        <div class="space-y-4">
          <div v-for="key in (['easy', 'medium', 'hard'] as const)" :key="key" class="flex items-center gap-3">
            <span class="w-12 text-sm text-slate-700">
              {{ key === 'easy' ? '易' : key === 'medium' ? '中' : '难' }}
            </span>
            <input
              v-model.number="difficulty[key]"
              type="range"
              min="0"
              max="1"
              step="0.01"
              class="flex-1"
              :disabled="readonly"
            />
            <span class="w-14 text-sm text-slate-600 text-right">{{ (Number(difficulty[key]) || 0).toFixed(2) }}</span>
          </div>
          <div class="flex h-3 w-full rounded-full overflow-hidden bg-slate-100">
            <div class="bg-emerald-300" :style="{ width: ((difficulty.easy / (sumDifficulty || 1)) * 100) + '%' }" />
            <div class="bg-amber-300" :style="{ width: ((difficulty.medium / (sumDifficulty || 1)) * 100) + '%' }" />
            <div class="bg-rose-300" :style="{ width: ((difficulty.hard / (sumDifficulty || 1)) * 100) + '%' }" />
          </div>
        </div>
      </section>

      <!-- 联网素养建议弹窗 -->
      <div
        v-if="suggestOpen"
        class="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4"
        @click.self="closeSuggest"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
          <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h3 class="text-base font-semibold text-slate-900">联网检索核心素养</h3>
              <p class="text-xs text-slate-500 mt-0.5">
                学科：{{ selectedPreset || '(未选择)' }} · 教材：{{ taskName || '(无)' }}
              </p>
            </div>
            <button
              class="text-slate-400 hover:text-slate-700 text-xl leading-none"
              @click="closeSuggest"
              aria-label="close"
            >
              ×
            </button>
          </div>
          <div class="px-5 py-4 space-y-3 overflow-auto">
            <div>
              <label class="text-xs text-slate-600 mb-1 block">
                教师个性化需求（可选，<span :class="suggestNeeds.length > NEEDS_MAX ? 'text-rose-600' : ''">{{ suggestNeeds.length }}/{{ NEEDS_MAX }}</span>）
              </label>
              <textarea
                v-model="suggestNeeds"
                :maxlength="NEEDS_MAX"
                rows="3"
                placeholder="例如：希望聚焦实验探究与跨学科应用，淡化纯记忆性内容"
                class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-slate-900"
              />
            </div>
            <div class="flex items-center gap-2">
              <button
                class="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
                :disabled="suggestLoading"
                @click="fetchSuggest"
              >
                {{ suggestLoading ? '检索中...' : '开始检索' }}
              </button>
              <span v-if="suggestState.source === 'cache'" class="text-xs text-emerald-600">
                来自本地缓存（24h 内同参数复用）
              </span>
              <span v-if="suggestState.source === 'live'" class="text-xs text-slate-500">
                来自联网检索
              </span>
            </div>
            <p v-if="suggestError" class="text-sm text-rose-600">{{ suggestError }}</p>
            <div v-if="suggestItems.length" class="space-y-2">
              <div class="flex items-center justify-between text-xs text-slate-500">
                <span>共 {{ suggestItems.length }} 条建议（可勾选）</span>
                <button
                  class="hover:underline"
                  @click="suggestItems.forEach((it) => (it._checked = !suggestItems.every((x) => x._checked)))"
                >
                  全选 / 全不选
                </button>
              </div>
              <div
                v-for="(it, i) in suggestItems"
                :key="i"
                class="border border-slate-200 rounded-xl p-3 hover:border-slate-400"
              >
                <label class="flex items-start gap-3 cursor-pointer">
                  <input v-model="it._checked" type="checkbox" class="mt-1" />
                  <div class="flex-1 min-w-0">
                    <div class="flex items-baseline gap-2 flex-wrap">
                      <span class="text-sm font-medium text-slate-900">{{ it.name }}</span>
                      <span v-if="it.dimension" class="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                        {{ it.dimension }}
                      </span>
                    </div>
                    <p v-if="it.description" class="text-xs text-slate-600 mt-1">{{ it.description }}</p>
                    <a
                      v-if="it.source_url"
                      :href="it.source_url"
                      target="_blank"
                      rel="noopener"
                      class="text-xs text-slate-500 hover:text-slate-900 underline mt-1 inline-block break-all"
                    >
                      {{ it.source_url }}
                    </a>
                  </div>
                </label>
              </div>
            </div>
          </div>
          <div class="px-5 py-3 border-t border-slate-200 flex items-center justify-end gap-2">
            <button
              class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900"
              @click="closeSuggest"
            >
              取消
            </button>
            <button
              class="px-3 py-1.5 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
              :disabled="!suggestItems.some((it) => it._checked)"
              @click="applySelectedSuggestions"
            >
              应用所选项
            </button>
          </div>
        </div>
      </div>

      <div class="mt-6 flex items-center justify-between gap-2 flex-wrap">
        <button
          class="px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900 disabled:opacity-50"
          :disabled="step === 1"
          @click="prev"
        >
          ← 上一步
        </button>
        <div class="flex items-center gap-2">
          <button
            v-if="!readonly && step === totalSteps"
            class="px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900 disabled:opacity-50"
            :disabled="submitting || !selectedPreset"
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
            :disabled="submitting || !selectedPreset"
            @click="saveAndRun"
          >
            {{ submitting ? '提交中...' : '保存并开始生成' }}
          </button>
          <button
            v-else
            class="px-4 py-2 text-sm bg-slate-300 text-white rounded-lg cursor-not-allowed"
            disabled
          >
            任务已启动，无法再次开始
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
