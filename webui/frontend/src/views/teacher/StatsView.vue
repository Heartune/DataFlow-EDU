<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '@/api/client';
import BarChartHorizontal from '@/components/charts/BarChartHorizontal.vue';
import DoughnutChart from '@/components/charts/DoughnutChart.vue';

const props = defineProps<{ id: string }>();

interface QuestionItem {
  _id?: string;
  _file?: string;
  question?: string;
  answer?: string;
  type?: string;
  options?: string[];
  category?: string;
  subcategory?: string;
  ability_main?: string;
  ability_level?: string;
  difficulty?: string | number;
  explanation?: string;
  source_page?: string | number;
  [k: string]: unknown;
}

interface TaskStats {
  stage: string;
  files: string[];
  total: number;
  levelDist: Record<string, number>;
  typeDist: Record<string, number>;
  diffDist: Record<string, number>;
  categoryDist: Record<string, number>;
  subcategoryDist: Record<string, number>;
  abilityMainDist: Record<string, number>;
  subjectiveRatio: string;
  items: QuestionItem[];
}

// ── 阶段选择（与 EditView 保持一致）────────────────────────────
const EXPORTABLE_STAGE_MAP: Record<string, { id: string; label: string }> = {
  '3.8 选择题格式检查':   { id: '3_8_mcq_verified',                      label: '3.8 选择题格式检查' },
  '3.7 多语言翻译':      { id: '3_7_translated',                        label: '3.7 多语言翻译' },
  '3.6 题库增强':        { id: '3_6_synthesized',                        label: '3.6 题库增强' },
  '3.5 去除重复题目':    { id: '3_5_deduplicated',                      label: '3.5 去除重复题目' },
  '3.4 考察领域修正':    { id: '3_4_domain_refined',                    label: '3.4 考察领域修正' },
  '3.2 题意模糊修正':    { id: '3_2_ambiguity_refined',                 label: '3.2 题意模糊修正' },
  '2.2 知识均衡检查与修正': { id: '2_1_generation/2_2_balanced',        label: '2.2 知识均衡检查与修正' },
  '2.2 知识均衡检查':      { id: '2_1_generation/2_2_balanced',          label: '2.2 知识均衡检查' },
  '2.1 题目生成':        { id: '2_1_generation/2_1_generated_stage_2',   label: '2.1 题目生成' },
};

type StageStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';

interface StageOption {
  id: string;
  label: string;
  status: StageStatus;
}

const availableStages = ref<StageOption[]>([]);
const selectedStage = ref('');

async function loadAvailableStages() {
  try {
    const { data } = await api.get(`/tasks/${encodeURIComponent(props.id)}`);
    const progressStages: { name: string; status: StageStatus }[] = data?.progress?.stages ?? [];
    const statusByName = new Map(progressStages.map((s) => [s.name, s.status]));

    const result: StageOption[] = [];
    for (const [stageName, { id, label }] of Object.entries(EXPORTABLE_STAGE_MAP)) {
      const status = statusByName.get(stageName);
      if (status === undefined) continue;
      if (status === 'skipped') continue;
      result.push({ id, label, status });
    }
    availableStages.value = result;

    const firstSucceeded = result.find((s) => s.status === 'succeeded');
    if (firstSucceeded) selectedStage.value = firstSucceeded.id;
    else if (result.length > 0) selectedStage.value = result[0].id;
  } catch {
    // 降级：不设阶段，让 stats 接口自动选
  }
}

// ── 统计数据 ───────────────────────────────────────────────────
const stats = ref<TaskStats | null>(null);
const loading = ref(false);
const error = ref('');

async function loadStats() {
  loading.value = true;
  error.value = '';
  try {
    const params: Record<string, string> = {};
    if (selectedStage.value) params.stage = selectedStage.value;
    const resp = await api.get(`/tasks/${props.id}/stats`, {
      params,
      validateStatus: (s) => s === 200 || s === 204,
    });
    if (resp.status === 204) {
      stats.value = null;
    } else {
      stats.value = resp.data as TaskStats;
    }
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载统计失败';
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadAvailableStages();
  await loadStats();
});

watch(selectedStage, async () => {
  await loadStats();
  // 清空选中和分页
  selectedIds.value = new Set();
  page.value = 1;
});

// ── 图表颜色 ──────────────────────────────────────────────────
const pieColors = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
  '#8B5CF6', '#EC4899', '#06B6D4', '#94A3B8',
];

const typeEntries = computed(() =>
  Object.entries(stats.value?.typeDist || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
);
const categoryEntries = computed(() =>
  Object.entries(stats.value?.categoryDist || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
);
const subcategoryEntries = computed(() =>
  Object.entries(stats.value?.subcategoryDist || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 20)
);
const abilityMainEntries = computed(() =>
  Object.entries(stats.value?.abilityMainDist || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
);
const levelEntries = computed(() =>
  Object.entries(stats.value?.levelDist || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
);

// ── 题目列表筛选/分页 ──────────────────────────────────────────
const PAGE_SIZE = 20;
const search = ref('');
const levelFilter = ref('');
const typeFilter = ref('');
const diffFilter = ref('');
const page = ref(1);

watch([search, levelFilter, typeFilter, diffFilter], () => { page.value = 1; });

const filteredItems = computed(() => {
  let qs = (stats.value?.items || []).slice();
  if (search.value)
    qs = qs.filter((q) => (q.question || '').toLowerCase().includes(search.value.toLowerCase()));
  if (levelFilter.value)
    qs = qs.filter((q) => q.ability_level === levelFilter.value);
  if (typeFilter.value)
    qs = qs.filter((q) => q.type === typeFilter.value);
  if (diffFilter.value)
    qs = qs.filter((q) => q.difficulty === diffFilter.value);
  return qs;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / PAGE_SIZE)));

const PAGINATION_WINDOW = 5;
const paginationPageNumbers = computed(() => {
  const n = totalPages.value;
  const p = page.value;
  const w = Math.min(PAGINATION_WINDOW, n);
  let start = p - Math.floor(w / 2);
  start = Math.max(1, Math.min(start, n - w + 1));
  return Array.from({ length: w }, (_, i) => start + i);
});

const pageItems = computed(() => {
  const p = Math.min(page.value, totalPages.value);
  return filteredItems.value.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE);
});

function setPage(p: number) {
  page.value = Math.max(1, Math.min(totalPages.value, p));
}

// ── 批量选中 ──────────────────────────────────────────────────
const selectedIds = ref<Set<string>>(new Set());

const allPageSelected = computed(() => {
  const ids = pageItems.value.map((q) => q._id).filter(Boolean);
  return ids.length > 0 && ids.every((id) => selectedIds.value.has(id as string));
});

function toggleSelectAll() {
  const ids = pageItems.value.map((q) => q._id).filter(Boolean) as string[];
  if (allPageSelected.value) {
    ids.forEach((id) => selectedIds.value.delete(id));
  } else {
    ids.forEach((id) => selectedIds.value.add(id));
  }
  selectedIds.value = new Set(selectedIds.value);
}

function toggleSelectOne(id: string) {
  if (selectedIds.value.has(id)) {
    selectedIds.value.delete(id);
  } else {
    selectedIds.value.add(id);
  }
  selectedIds.value = new Set(selectedIds.value);
}

// ── 删除 ───────────────────────────────────────────────────────
const deleting = ref(false);
const actionMsg = ref('');
const actionError = ref('');

function clearMsg() {
  setTimeout(() => {
    actionMsg.value = '';
    actionError.value = '';
  }, 3000);
}

async function deleteSelected() {
  const ids = Array.from(selectedIds.value);
  if (!ids.length) return;
  if (!window.confirm(`确认删除选中的 ${ids.length} 道题目？后台会先备份原文件。`)) return;
  deleting.value = true;
  actionError.value = '';
  let ok = 0;
  for (const id of ids) {
    const item = stats.value?.items.find((q) => q._id === id);
    if (!item?._file) continue;
    try {
      await api.delete(`/tasks/${props.id}/items/${id}`, {
        params: { stage: stats.value!.stage, file: item._file },
      });
      ok++;
    } catch {
      // 单条失败不打断其它
    }
  }
  if (stats.value) {
    stats.value.items = stats.value.items.filter((q) => !selectedIds.value.has(q._id as string));
    stats.value.total = stats.value.items.length;
  }
  selectedIds.value = new Set();
  deleting.value = false;
  actionMsg.value = `已删除 ${ok}/${ids.length} 道题目`;
  clearMsg();
}

// ── 编辑 Modal ─────────────────────────────────────────────────
const QUESTION_TYPES = ['选择题', '判断题', '填空题', '简答题', '综合题', '计算题'];
const DIFFICULTIES = ['易', '中', '难'];

interface EditState {
  isNew: boolean;
  item: QuestionItem;
  orig: QuestionItem | null;
  saving: boolean;
  saveError: string;
}

const editState = ref<EditState | null>(null);

function openEdit(q: QuestionItem) {
  const copy = JSON.parse(JSON.stringify(q)) as QuestionItem;
  // 确保 options 是数组
  if (!Array.isArray(copy.options)) copy.options = [];
  editState.value = {
    isNew: false,
    item: copy,
    orig: JSON.parse(JSON.stringify(copy)),
    saving: false,
    saveError: '',
  };
}

function openNewQuestion() {
  const file = stats.value?.files?.[0] ?? '';
  editState.value = {
    isNew: true,
    item: {
      _file: file,
      question: '',
      type: '选择题',
      options: ['', '', '', ''],
      answer: '',
      explanation: '',
      difficulty: '中',
    },
    orig: null,
    saving: false,
    saveError: '',
  };
}

function hasChanges(): boolean {
  if (!editState.value || editState.value.isNew) return false;
  return JSON.stringify(editState.value.item) !== JSON.stringify(editState.value.orig);
}

/** 关闭时自动保存（已有题目）；新增题目需手动点「保存」 */
async function closeEdit() {
  if (!editState.value) return;
  if (editState.value.isNew) {
    editState.value = null;
    return;
  }
  if (hasChanges()) {
    await saveEdit();
  } else {
    editState.value = null;
  }
}

async function saveEdit() {
  if (!editState.value || !stats.value) return;
  const { isNew, item } = editState.value;
  const stage = stats.value.stage;
  const file = item._file as string;

  if (!file) {
    editState.value.saveError = '无法确定文件路径，请刷新后重试';
    return;
  }

  editState.value.saving = true;
  editState.value.saveError = '';

  // 清理内部字段，不提交到服务端
  const payload = { ...item };
  delete payload._id;
  delete payload._file;

  // 清理 options：去掉空字符串
  if (Array.isArray(payload.options)) {
    payload.options = (payload.options as string[]).filter((o) => o.trim() !== '');
    if (payload.options.length === 0) delete payload.options;
  }

  try {
    if (isNew) {
      const { data } = await api.post(`/tasks/${props.id}/items`, payload, {
        params: { stage, file },
      });
      const created = data.item as QuestionItem;
      stats.value.items.unshift(created);
      stats.value.total += 1;
      editState.value = null;
      actionMsg.value = '已新增题目';
      clearMsg();
    } else {
      const id = editState.value.orig?._id ?? editState.value.item._id;
      const { data } = await api.patch(`/tasks/${props.id}/items/${id}`, payload, {
        params: { stage, file },
      });
      const updated = data.item as QuestionItem;
      // 更新本地列表
      const idx = stats.value.items.findIndex((q) => q._id === id);
      if (idx >= 0) {
        stats.value.items[idx] = { ...updated, _file: file };
      }
      editState.value = null;
      actionMsg.value = '已保存';
      clearMsg();
    }
  } catch (err: any) {
    if (editState.value) {
      editState.value.saveError = err?.response?.data?.error || err?.message || '保存失败';
      editState.value.saving = false;
    }
  }
}

function setOptionValue(idx: number, val: string) {
  if (!editState.value) return;
  const opts = [...(editState.value.item.options as string[] || [])];
  opts[idx] = val;
  editState.value.item.options = opts;
}

function addOption() {
  if (!editState.value) return;
  const opts = [...(editState.value.item.options as string[] || [])];
  opts.push('');
  editState.value.item.options = opts;
}

function removeOption(idx: number) {
  if (!editState.value) return;
  const opts = [...(editState.value.item.options as string[] || [])];
  opts.splice(idx, 1);
  editState.value.item.options = opts;
}

const isMcq = computed(() => {
  if (!editState.value) return false;
  const t = editState.value.item.type;
  return t === '选择题' || t === '判断题';
});
</script>

<template>
  <div>
    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-16 text-slate-400 text-sm gap-2">
      <span class="inline-block w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" />
      正在加载统计数据…
    </div>

    <!-- 出错 -->
    <div v-else-if="error" class="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4">
      {{ error }}
    </div>

    <!-- 无数据 -->
    <div v-else-if="!stats" class="flex flex-col items-center justify-center py-16 text-slate-400 gap-2">
      <i class="fa-solid fa-chart-bar text-3xl" />
      <p class="text-sm">暂无统计数据，请等待任务至少完成一个生成阶段。</p>
    </div>

    <!-- 统计内容 -->
    <template v-else>
      <!-- 阶段选择器 -->
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <label class="text-sm text-slate-600 flex items-center gap-2">
          <i class="fa-solid fa-layer-group text-slate-400" />
          数据阶段
          <select
            v-model="selectedStage"
            class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm bg-white"
            :disabled="availableStages.length === 0"
          >
            <option v-if="availableStages.length === 0" value="">（暂无可用阶段）</option>
            <option
              v-for="s in availableStages"
              :key="s.id"
              :value="s.id"
              :disabled="s.status !== 'succeeded'"
            >
              {{ s.label }}{{ s.status !== 'succeeded' ? `（${s.status === 'pending' ? '尚未运行' : s.status === 'running' ? '运行中' : s.status === 'failed' ? '运行失败' : s.status}）` : '' }}
            </option>
          </select>
        </label>
      </div>

      <!-- 操作反馈 -->
      <p v-if="actionMsg" class="text-sm text-emerald-600 mb-3">{{ actionMsg }}</p>
      <p v-if="actionError" class="text-sm text-rose-600 mb-3">{{ actionError }}</p>

      <div class="space-y-5">
        <!-- 统计卡片 + 题型图 -->
        <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="grid grid-cols-2 gap-4">
            <div
              v-for="c in [
                {
                  label: '总题目数',
                  value: stats?.total ?? 0,
                  sub: `覆盖 ${Object.keys(stats?.categoryDist || {}).filter((k) => (stats?.categoryDist || {})[k] > 0).length} 个知识大类、${Object.keys(stats?.subcategoryDist || {}).filter((k) => (stats?.subcategoryDist || {})[k] > 0).length} 个知识小类`,
                  icon: 'list',
                  accent: 'blue',
                },
                {
                  label: '能力层级种类',
                  value: Object.keys(stats?.levelDist || {}).filter((k) => (stats?.levelDist || {})[k] > 0).length,
                  sub: Object.keys(stats?.levelDist || {}).filter((k) => (stats?.levelDist || {})[k] > 0).length >= 16 ? '已全覆盖' : `未全覆盖（已 ${Object.keys(stats?.levelDist || {}).filter((k) => (stats?.levelDist || {})[k] > 0).length}/16 种）`,
                  icon: 'pie',
                  accent: 'indigo',
                },
                {
                  label: '主观题占比',
                  value: (stats?.subjectiveRatio ?? 0) + '%',
                  sub: `主观题 ${Math.round((stats?.total ?? 0) * (parseInt(stats?.subjectiveRatio ?? '0') / 100))} 道 / 客观题 ${(stats?.total ?? 0) - Math.round((stats?.total ?? 0) * (parseInt(stats?.subjectiveRatio ?? '0') / 100))} 道`,
                  icon: 'edit',
                  accent: 'amber',
                  bar: parseInt(stats?.subjectiveRatio ?? '0'),
                },
                {
                  label: '难度分布',
                  value: `易${stats?.diffDist?.['易'] ?? 0} / 中${stats?.diffDist?.['中'] ?? 0} / 难${stats?.diffDist?.['难'] ?? 0}`,
                  sub: `易 ${stats?.total ? Math.round(((stats?.diffDist?.['易'] ?? 0) / stats.total) * 100) : 0}% · 中 ${stats?.total ? Math.round(((stats?.diffDist?.['中'] ?? 0) / stats.total) * 100) : 0}% · 难 ${stats?.total ? Math.round(((stats?.diffDist?.['难'] ?? 0) / stats.total) * 100) : 0}%`,
                  icon: 'bar',
                  accent: 'emerald',
                },
              ]"
              :key="c.label"
              class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <p class="text-xs font-medium text-slate-500">{{ c.label }}</p>
                  <p class="text-xl font-bold text-slate-900 mt-0.5">{{ c.value }}</p>
                  <p class="text-xs text-slate-400 mt-1 truncate" :title="c.sub">{{ c.sub }}</p>
                  <div v-if="c.bar !== undefined" class="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div class="h-full rounded-full bg-amber-400" :style="{ width: Math.min(100, c.bar) + '%' }" />
                  </div>
                </div>
                <div
                  class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                  :class="{
                    'bg-blue-100 text-blue-600': c.accent === 'blue',
                    'bg-indigo-100 text-indigo-600': c.accent === 'indigo',
                    'bg-amber-100 text-amber-600': c.accent === 'amber',
                    'bg-emerald-100 text-emerald-600': c.accent === 'emerald',
                  }"
                >
                  <i v-if="c.icon === 'list'" class="fa-solid fa-list text-lg" aria-hidden="true" />
                  <i v-else-if="c.icon === 'pie'" class="fa-solid fa-chart-pie text-lg" aria-hidden="true" />
                  <i v-else-if="c.icon === 'edit'" class="fa-solid fa-pen text-lg" aria-hidden="true" />
                  <i v-else-if="c.icon === 'bar'" class="fa-solid fa-chart-column text-lg" aria-hidden="true" />
                </div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up">
            <h3 class="text-sm font-semibold text-slate-800 mb-4">题型分布</h3>
            <div v-if="typeEntries.length" class="h-[300px]">
              <BarChartHorizontal
                :labels="typeEntries.map(([k]) => k)"
                :data="typeEntries.map(([, v]) => v)"
                border-color="#10B981"
                background-color="#10B98120"
              />
            </div>
            <div v-else class="text-slate-400 text-xs">暂无数据</div>
          </div>
        </section>

        <!-- 知识方向分布 -->
        <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up">
            <h3 class="text-sm font-semibold text-slate-800 mb-4">知识方向分布（大类）</h3>
            <div v-if="categoryEntries.length" class="h-[220px] flex items-center justify-center">
              <div class="h-[200px] w-[200px]">
                <DoughnutChart
                  :labels="categoryEntries.map(([k]) => k.length > 18 ? k.slice(0, 18) + '...' : k)"
                  :data="categoryEntries.map(([, v]) => v)"
                  :colors="pieColors"
                />
              </div>
            </div>
            <div class="mt-4 space-y-2 text-xs">
              <div v-for="([k, v], i) in categoryEntries" :key="k" class="flex items-center justify-between gap-3">
                <span class="flex items-center gap-2 min-w-0">
                  <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :style="{ background: pieColors[i % pieColors.length] }" />
                  <span class="text-slate-600 truncate">{{ k }}</span>
                </span>
                <span class="font-medium text-slate-800 flex-shrink-0">
                  {{ v }} ({{ categoryEntries.reduce((s, [, vv]) => s + vv, 0) ? ((v / categoryEntries.reduce((s, [, vv]) => s + vv, 0)) * 100).toFixed(1) : 0 }}%)
                </span>
              </div>
            </div>
            <div v-if="!categoryEntries.length" class="text-slate-400 text-xs">暂无数据</div>
          </div>

          <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col">
            <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">知识方向分布（小类）</h3>
            <div v-if="subcategoryEntries.length" class="flex-1 min-h-[300px] flex items-center justify-center">
              <div class="w-full h-[300px]">
                <BarChartHorizontal
                  :labels="subcategoryEntries.map(([k]) => k.length > 18 ? k.slice(0, 18) + '...' : k)"
                  :data="subcategoryEntries.map(([, v]) => v)"
                  border-color="#2563EB"
                  background-color="#3B82F633"
                />
              </div>
            </div>
            <div v-if="!subcategoryEntries.length" class="text-slate-400 text-xs">暂无数据</div>
          </div>
        </section>

        <!-- 能力层级分布 -->
        <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up">
            <h3 class="text-sm font-semibold text-slate-800 mb-4">能力主层级分布</h3>
            <div v-if="abilityMainEntries.length" class="h-[220px] flex items-center justify-center">
              <div class="h-[200px] w-[200px]">
                <DoughnutChart
                  :labels="abilityMainEntries.map(([k]) => k.length > 12 ? k.slice(0, 12) + '...' : k)"
                  :data="abilityMainEntries.map(([, v]) => v)"
                  :colors="pieColors"
                />
              </div>
            </div>
            <div class="mt-4 space-y-2">
              <div v-for="([k, v], i) in abilityMainEntries" :key="k" class="flex items-center justify-between gap-3 text-xs">
                <span class="flex items-center gap-2 min-w-0">
                  <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :style="{ background: pieColors[i % pieColors.length] }" />
                  <span class="text-slate-600 truncate">{{ k }}</span>
                </span>
                <span class="font-medium text-slate-800 flex-shrink-0">
                  {{ v }} ({{ abilityMainEntries.reduce((s, [, vv]) => s + vv, 0) ? ((v / abilityMainEntries.reduce((s, [, vv]) => s + vv, 0)) * 100).toFixed(1) : 0 }}%)
                </span>
              </div>
            </div>
            <div v-if="!abilityMainEntries.length" class="text-slate-400 text-xs">暂无数据</div>
          </div>

          <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col">
            <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">能力子层级分布</h3>
            <div v-if="levelEntries.length" class="flex-1 min-h-[300px] flex items-center justify-center">
              <div class="w-full h-[300px]">
                <BarChartHorizontal
                  :labels="levelEntries.map(([k]) => k.length > 14 ? k.slice(0, 14) + '...' : k)"
                  :data="levelEntries.map(([, v]) => v)"
                  border-color="#10B981"
                  background-color="#10B98133"
                />
              </div>
            </div>
            <div v-if="!levelEntries.length" class="text-slate-400 text-xs">暂无数据</div>
          </div>
        </section>

        <!-- 题目列表 -->
        <section class="bg-white rounded-xl shadow-sm border border-slate-200/60 animate-fade-in-up">
          <div class="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div class="flex items-center gap-3 flex-wrap">
              <h3 class="text-sm font-semibold text-slate-800">题目列表</h3>
              <!-- 批量删除 -->
              <button
                v-if="selectedIds.size > 0"
                class="px-3 py-1 text-xs rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-50 disabled:opacity-50 transition"
                :disabled="deleting"
                @click="deleteSelected"
              >
                <i class="fa-solid fa-trash-can mr-1" />
                删除选中 ({{ selectedIds.size }})
              </button>
              <!-- 新增题目 -->
              <button
                v-if="stats?.files?.length"
                class="px-3 py-1 text-xs rounded-lg border border-slate-300 text-slate-700 hover:border-slate-900 hover:bg-slate-50 transition"
                @click="openNewQuestion"
              >
                <i class="fa-solid fa-plus mr-1" />
                新增题目
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-2 w-full sm:w-auto">
              <input
                v-model="search"
                type="search"
                placeholder="搜索题目内容..."
                class="w-full sm:w-44 pl-3 pr-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300/40 focus:border-slate-400"
              />
              <select
                v-model="levelFilter"
                class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
              >
                <option value="">全部能力层级</option>
                <option
                  v-for="l in Object.keys(stats?.levelDist || {}).filter((k) => (stats?.levelDist || {})[k] > 0).sort()"
                  :key="l"
                  :value="l"
                >{{ l }}</option>
              </select>
              <select
                v-model="typeFilter"
                class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
              >
                <option value="">全部题型</option>
                <option
                  v-for="t in Object.keys(stats?.typeDist || {}).filter((k) => (stats?.typeDist || {})[k] > 0).sort()"
                  :key="t"
                  :value="t"
                >{{ t }}</option>
              </select>
              <select
                v-model="diffFilter"
                class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
              >
                <option value="">全部难度</option>
                <option v-for="d in ['易', '中', '难'].filter((x) => (stats?.diffDist || {})[x] > 0)" :key="d" :value="d">{{ d }}</option>
              </select>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
              <thead>
                <tr class="bg-slate-50/60 border-b border-slate-100">
                  <th class="px-3 py-2.5 w-10">
                    <input
                      type="checkbox"
                      class="rounded border-slate-300 cursor-pointer"
                      :checked="allPageSelected"
                      :indeterminate="selectedIds.size > 0 && !allPageSelected"
                      @change="toggleSelectAll"
                    />
                  </th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-10 text-center">#</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 min-w-[280px]">题目</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-20">题型</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-28">知识小类</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-32">能力层级</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-14 text-center">难度</th>
                  <th class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-20">来源页</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!pageItems.length">
                  <td colspan="8" class="px-4 py-10 text-center text-sm text-slate-400">无匹配数据</td>
                </tr>
                <tr
                  v-for="(q, i) in pageItems"
                  :key="q._id ?? i"
                  class="border-b border-slate-50 hover:bg-slate-50/60 transition-colors"
                  :class="{ 'bg-slate-50': q._id && selectedIds.has(q._id) }"
                >
                  <td class="px-3 py-3" @click.stop>
                    <input
                      v-if="q._id"
                      type="checkbox"
                      class="rounded border-slate-300 cursor-pointer"
                      :checked="selectedIds.has(q._id)"
                      @change="toggleSelectOne(q._id)"
                    />
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-400 text-center">
                    {{ (page - 1) * PAGE_SIZE + i + 1 }}
                  </td>
                  <td class="px-3 py-3 text-sm text-slate-800 cursor-pointer" @click="openEdit(q)">
                    <div class="line-clamp-2">{{ q.question || '' }}</div>
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-600 cursor-pointer" @click="openEdit(q)">{{ q.type || '-' }}</td>
                  <td class="px-3 py-3 text-xs text-slate-600 cursor-pointer" @click="openEdit(q)">
                    {{ (q.subcategory || '-').length > 12 ? (q.subcategory || '').slice(0, 12) + '...' : (q.subcategory || '-') }}
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-600 cursor-pointer" @click="openEdit(q)">
                    {{ (q.ability_level || '-').length > 14 ? (q.ability_level || '').slice(0, 14) + '...' : (q.ability_level || '-') }}
                  </td>
                  <td class="px-3 py-3 text-xs text-center cursor-pointer" @click="openEdit(q)">
                    <span
                      :class="[
                        'px-2 py-0.5 rounded',
                        q.difficulty === '难' ? 'bg-red-100 text-red-700'
                          : q.difficulty === '易' ? 'bg-green-100 text-green-700'
                          : 'bg-slate-100 text-slate-600',
                      ]"
                    >{{ q.difficulty || '-' }}</span>
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-500 cursor-pointer" @click="openEdit(q)">{{ q.source_page || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="px-3 py-2 border-t border-slate-100 flex items-center justify-between">
            <span class="text-xs text-slate-400">共 {{ filteredItems.length }} 道题目</span>
            <div v-if="totalPages > 1" class="flex items-center gap-1">
              <button
                :disabled="page <= 1"
                :class="['px-2 py-1 text-xs rounded', page <= 1 ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100']"
                @click="setPage(page - 1)"
              >‹</button>
              <button
                v-for="pn in paginationPageNumbers"
                :key="pn"
                :class="[
                  'px-2 py-1 text-xs rounded',
                  page === pn
                    ? 'bg-slate-900 text-white'
                    : 'text-slate-600 hover:bg-slate-100',
                ]"
                @click="setPage(pn)"
              >{{ pn }}</button>
              <button
                :disabled="page >= totalPages"
                :class="['px-2 py-1 text-xs rounded', page >= totalPages ? 'text-slate-300 cursor-not-allowed' : 'text-slate-600 hover:bg-slate-100']"
                @click="setPage(page + 1)"
              >›</button>
            </div>
          </div>
        </section>
      </div>
    </template>

    <!-- 编辑 / 新增 Modal -->
    <Teleport to="body">
      <div
        v-if="editState"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @click.self="closeEdit"
      >
        <div class="absolute inset-0 bg-black/40" @click="closeEdit" />
        <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
          <!-- Modal 顶栏 -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
            <h2 class="text-sm font-semibold text-slate-800">
              {{ editState.isNew ? '新增题目' : '编辑题目' }}
              <span v-if="!editState.isNew && hasChanges()" class="ml-2 text-xs font-normal text-amber-500">有未保存的修改，关闭时自动保存</span>
            </h2>
            <button
              class="text-slate-400 hover:text-slate-700 transition"
              :disabled="editState.saving"
              @click="closeEdit"
            >
              <i class="fa-solid fa-xmark text-lg" />
            </button>
          </div>

          <!-- Modal 内容 -->
          <div class="overflow-y-auto flex-1 px-6 py-5 space-y-4 text-sm">
            <!-- 题型 + 难度 -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-semibold text-slate-500 mb-1.5">题型</label>
                <select
                  v-model="editState.item.type"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
                >
                  <option v-for="t in QUESTION_TYPES" :key="t" :value="t">{{ t }}</option>
                  <option v-if="editState.item.type && !QUESTION_TYPES.includes(editState.item.type as string)" :value="editState.item.type">{{ editState.item.type }}</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-500 mb-1.5">难度</label>
                <select
                  v-model="editState.item.difficulty"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
                >
                  <option v-for="d in DIFFICULTIES" :key="d" :value="d">{{ d }}</option>
                </select>
              </div>
            </div>

            <!-- 题干 -->
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1.5">题干</label>
              <textarea
                v-model="editState.item.question"
                rows="12"
                class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm leading-relaxed focus:outline-none focus:border-slate-400 resize-y"
                placeholder="请输入题干内容…"
              />
            </div>

            <!-- 选项（客观题） -->
            <div v-if="isMcq">
              <div class="flex items-center justify-between mb-1.5">
                <label class="text-xs font-semibold text-slate-500">选项</label>
                <button
                  type="button"
                  class="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1"
                  @click="addOption"
                >
                  <i class="fa-solid fa-plus" /> 添加选项
                </button>
              </div>
              <div class="space-y-2">
                <div
                  v-for="(opt, oi) in (editState.item.options as string[] || [])"
                  :key="oi"
                  class="flex items-center gap-2"
                >
                  <span class="text-xs font-medium text-slate-400 w-5 flex-shrink-0 text-center">{{ String.fromCharCode(65 + oi) }}</span>
                  <input
                    type="text"
                    :value="opt"
                    class="flex-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-slate-400"
                    :placeholder="`选项 ${String.fromCharCode(65 + oi)}`"
                    @input="setOptionValue(oi, ($event.target as HTMLInputElement).value)"
                  />
                  <button
                    type="button"
                    class="text-slate-300 hover:text-rose-500 transition flex-shrink-0"
                    @click="removeOption(oi)"
                  >
                    <i class="fa-solid fa-xmark" />
                  </button>
                </div>
                <div v-if="!(editState.item.options as string[])?.length" class="text-xs text-slate-400">
                  暂无选项，点击「添加选项」
                </div>
              </div>
            </div>

            <!-- 答案 -->
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1.5">答案</label>
              <textarea
                v-model="editState.item.answer"
                rows="8"
                class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm leading-relaxed focus:outline-none focus:border-slate-400 resize-y"
                placeholder="请输入答案…"
              />
            </div>

            <!-- 解析 -->
            <div>
              <label class="block text-xs font-semibold text-slate-500 mb-1.5">解析</label>
              <textarea
                v-model="editState.item.explanation"
                rows="8"
                class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm leading-relaxed focus:outline-none focus:border-slate-400 resize-y"
                placeholder="请输入解析（可选）…"
              />
            </div>

            <!-- 只读标签（知识点/能力）-->
            <div v-if="!editState.isNew" class="flex flex-wrap gap-2 pt-1 border-t border-slate-100">
              <span v-if="editState.item.category" class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">{{ editState.item.category }}</span>
              <span v-if="editState.item.subcategory" class="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs">{{ editState.item.subcategory }}</span>
              <span v-if="editState.item.ability_main" class="px-2 py-0.5 bg-violet-50 text-violet-700 rounded text-xs">{{ editState.item.ability_main }}</span>
              <span v-if="editState.item.ability_level" class="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-xs">{{ editState.item.ability_level }}</span>
              <span v-if="editState.item.source_page" class="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">第 {{ editState.item.source_page }} 页</span>
            </div>

            <!-- 错误信息 -->
            <p v-if="editState.saveError" class="text-sm text-rose-600">{{ editState.saveError }}</p>
          </div>

          <!-- Modal 底栏（新增题目时显示保存按钮；编辑时关闭即自动保存） -->
          <div v-if="editState.isNew" class="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 flex-shrink-0">
            <button
              type="button"
              class="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              :disabled="editState.saving"
              @click="editState = null"
            >
              取消
            </button>
            <button
              type="button"
              class="px-4 py-2 text-sm rounded-lg bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
              :disabled="editState.saving || !editState.item.question"
              @click="saveEdit"
            >
              {{ editState.saving ? '保存中…' : '创建题目' }}
            </button>
          </div>
          <div v-else class="flex items-center justify-between px-6 py-3 border-t border-slate-100 flex-shrink-0 bg-slate-50/60">
            <p class="text-xs text-slate-400">关闭时自动保存修改</p>
            <button
              type="button"
              class="px-4 py-2 text-sm rounded-lg bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
              :disabled="editState.saving"
              @click="closeEdit"
            >
              {{ editState.saving ? '保存中…' : '完成' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
