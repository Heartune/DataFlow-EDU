<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '@/api/client';

const props = defineProps<{
  id: string;
  taskStatus?: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  taskName?: string;
}>();

const router = useRouter();

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
        <h2 class="text-lg font-semibold text-slate-900 mb-1">第 2 步 · 核心素养</h2>
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
