<script setup lang="ts">
import { computed, watch } from 'vue';
import { usePipelineStore } from '@/stores/pipeline';
import { useQuestionSidebar } from '@/stores/questionSidebar';
import BarChartHorizontal from './charts/BarChartHorizontal.vue';
import DoughnutChart from './charts/DoughnutChart.vue';

const store = usePipelineStore();
const sidebarStore = useQuestionSidebar();
const stats = computed(() => store.stage3Stats);
const allQuestions = computed(() => store.stage3FilteredQuestions);
const pageQuestions = computed(() => store.stage3PaginatedQuestions);
const page = computed(() => store.stage3Page);
const totalPages = computed(() =>
  Math.max(1, Math.ceil(allQuestions.value.length / store.PAGE_SIZE))
);

watch(
  () => [store.stage3Search, store.stage3LevelFilter, store.stage3TypeFilter, store.stage3DiffFilter],
  () => { store.stage3Page = 1; }
);

const pieColors = [
  '#3B82F6',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#EC4899',
  '#06B6D4',
  '#94A3B8',
];

const typeEntries = computed(() =>
  Object.entries(stats.value?.typeDist || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
);

const categoryEntries = computed(() =>
  Object.entries(stats.value?.categoryDist || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
);

const subcategoryEntries = computed(() =>
  Object.entries(stats.value?.subcategoryDist || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
);

const abilityMainEntries = computed(() =>
  Object.entries(stats.value?.abilityMainDist || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
);

const levelEntries = computed(() =>
  Object.entries(stats.value?.levelDist || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
);

function setPage(p: number) {
  store.stage3Page = p;
}

function openQuestion(q: import('@/types/pipeline').Question) {
  sidebarStore.open(q);
}
</script>

<template>
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-5">
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
              <p class="text-xs text-slate-400 mt-1 truncate" :title="c.sub">
                {{ c.sub }}
              </p>
              <div
                v-if="c.bar !== undefined"
                class="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden"
              >
                <div
                  class="h-full rounded-full bg-amber-400"
                  :style="{ width: Math.min(100, c.bar) + '%' }"
                />
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
              <i v-if="c.icon === 'list'" class="fa-solid fa-list text-lg" aria-hidden="true"></i>
              <i v-else-if="c.icon === 'pie'" class="fa-solid fa-chart-pie text-lg" aria-hidden="true"></i>
              <i v-else-if="c.icon === 'edit'" class="fa-solid fa-pen text-lg" aria-hidden="true"></i>
              <i v-else-if="c.icon === 'bar'" class="fa-solid fa-chart-column text-lg" aria-hidden="true"></i>
            </div>
          </div>
        </div>
      </div>
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4">题型分布</h3>
        <div v-if="typeEntries.length" class="h-[300px]">
          <BarChartHorizontal
            :labels="typeEntries.map(([k]) => k)"
            :data="typeEntries.map(([, v]) => v)"
            border-color="#10B981"
            background-color="#10B98120"
          />
        </div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4">
          知识方向分布（大类）
        </h3>
        <div
          v-if="categoryEntries.length"
          class="h-[220px] flex items-center justify-center"
        >
          <div class="h-[200px] w-[200px]">
            <DoughnutChart
              :labels="
                categoryEntries.map(([k]) =>
                  k.length > 18 ? k.slice(0, 18) + '...' : k
                )
              "
              :data="categoryEntries.map(([, v]) => v)"
              :colors="pieColors"
            />
          </div>
        </div>
        <div class="mt-4 space-y-2 text-xs">
          <div
            v-for="([k, v], i) in categoryEntries"
            :key="k"
            class="flex items-center justify-between gap-3"
          >
            <span class="flex items-center gap-2 min-w-0">
              <span
                class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                :style="{ background: pieColors[i % pieColors.length] }"
              />
              <span class="text-slate-600 truncate">{{ k }}</span>
            </span>
            <span class="font-medium text-slate-800 flex-shrink-0">
              {{ v }}
              ({{
                categoryEntries.reduce((s, [, vv]) => s + vv, 0)
                  ? (
                      (v /
                        categoryEntries.reduce((s, [, vv]) => s + vv, 0)) *
                      100
                    ).toFixed(1)
                  : 0
              }}%)
            </span>
          </div>
        </div>
        <div v-if="!categoryEntries.length" class="text-slate-400 text-xs">
          暂无数据
        </div>
      </div>
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          知识方向分布（小类）
        </h3>
        <div
          v-if="subcategoryEntries.length"
          class="flex-1 min-h-[300px] flex items-center justify-center"
        >
          <div class="w-full h-[300px]">
            <BarChartHorizontal
              :labels="
                subcategoryEntries.map(([k]) =>
                  k.length > 18 ? k.slice(0, 18) + '...' : k
                )
              "
              :data="subcategoryEntries.map(([, v]) => v)"
              border-color="#2563EB"
              background-color="#3B82F633"
            />
          </div>
        </div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4">
          能力主层级分布
        </h3>
        <div
          v-if="abilityMainEntries.length"
          class="h-[220px] flex items-center justify-center"
        >
          <div class="h-[200px] w-[200px]">
            <DoughnutChart
              :labels="
                abilityMainEntries.map(([k]) =>
                  k.length > 12 ? k.slice(0, 12) + '...' : k
                )
              "
              :data="abilityMainEntries.map(([, v]) => v)"
              :colors="pieColors"
            />
          </div>
        </div>
        <div class="mt-4 space-y-2">
          <div
            v-for="([k, v], i) in abilityMainEntries"
            :key="k"
            class="flex items-center justify-between gap-3 text-xs"
          >
            <span class="flex items-center gap-2 min-w-0">
              <span
                class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                :style="{ background: pieColors[i % pieColors.length] }"
              />
              <span class="text-slate-600 truncate">{{ k }}</span>
            </span>
            <span class="font-medium text-slate-800 flex-shrink-0">
              {{ v }}
              ({{
                abilityMainEntries.reduce((s, [, vv]) => s + vv, 0)
                  ? (
                      (v /
                        abilityMainEntries.reduce((s, [, vv]) => s + vv, 0)) *
                      100
                    ).toFixed(1)
                  : 0
              }}%)
            </span>
          </div>
        </div>
        <div v-if="!abilityMainEntries.length" class="text-slate-400 text-xs">
          暂无数据
        </div>
      </div>
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          能力子层级分布
        </h3>
        <div
          v-if="levelEntries.length"
          class="flex-1 min-h-[300px] flex items-center justify-center"
        >
          <div class="w-full h-[300px]">
            <BarChartHorizontal
              :labels="
                levelEntries.map(([k]) =>
                  k.length > 14 ? k.slice(0, 14) + '...' : k
                )
              "
              :data="levelEntries.map(([, v]) => v)"
              border-color="#10B981"
              background-color="#10B98133"
            />
          </div>
        </div>
      </div>
    </section>

    <section
      class="bg-white rounded-xl shadow-sm border border-slate-200/60 animate-fade-in-up"
    >
      <div
        class="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
      >
        <h3 class="text-sm font-semibold text-slate-800">题目列表</h3>
        <div class="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          <input
            v-model="store.stage3Search"
            type="search"
            placeholder="搜索题目内容..."
            class="w-full sm:w-44 pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400"
          />
          <select
            v-model="store.stage3LevelFilter"
            class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">全部能力层级</option>
            <option
              v-for="l in Object.keys(stats?.levelDist || {}).filter(
                (k) => (stats?.levelDist || {})[k] > 0
              ).sort()"
              :key="l"
              :value="l"
            >
              {{ l }}
            </option>
          </select>
          <select
            v-model="store.stage3TypeFilter"
            class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">全部题型</option>
            <option
              v-for="t in Object.keys(stats?.typeDist || {}).filter(
                (k) => (stats?.typeDist || {})[k] > 0
              ).sort()"
              :key="t"
              :value="t"
            >
              {{ t }}
            </option>
          </select>
          <select
            v-model="store.stage3DiffFilter"
            class="px-2 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">全部难度</option>
            <option
              v-for="d in ['易', '中', '难'].filter(
                (x) => (stats?.diffDist || {})[x] > 0
              )"
              :key="d"
              :value="d"
            >
              {{ d }}
            </option>
          </select>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50/60 border-b border-slate-100">
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-12 text-center"
              >
                #
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 min-w-[280px]"
              >
                题目
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-20"
              >
                题型
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-28"
              >
                知识小类
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-32"
              >
                能力层级
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-14 text-center"
              >
                难度
              </th>
              <th
                class="px-3 py-2.5 text-xs font-semibold text-slate-500 w-20"
              >
                来源页
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!pageQuestions.length">
              <td
                colspan="7"
                class="px-4 py-10 text-center text-sm text-slate-400"
              >
                无匹配数据
              </td>
            </tr>
            <tr
              v-for="(q, i) in pageQuestions"
              :key="i"
              class="border-b border-slate-50 hover:bg-slate-50/60 transition-colors cursor-pointer"
              @click="openQuestion(q)"
            >
              <td class="px-3 py-3 text-xs text-slate-400 text-center">
                {{ (page - 1) * store.PAGE_SIZE + i + 1 }}
              </td>
              <td class="px-3 py-3 text-sm text-slate-800">
                <div class="truncate-2">{{ q.question || '' }}</div>
              </td>
              <td class="px-3 py-3 text-xs text-slate-600">{{ q.type || '-' }}</td>
              <td class="px-3 py-3 text-xs text-slate-600">
                {{ (q.subcategory || '-').length > 12 ? (q.subcategory || '').slice(0, 12) + '...' : (q.subcategory || '-') }}
              </td>
              <td class="px-3 py-3 text-xs text-slate-600">
                {{ (q.ability_level || '-').length > 14 ? (q.ability_level || '').slice(0, 14) + '...' : (q.ability_level || '-') }}
              </td>
              <td class="px-3 py-3 text-xs text-center">
                <span
                  :class="[
                    'px-2 py-0.5 rounded',
                    q.difficulty === '难'
                      ? 'bg-red-100 text-red-700'
                      : q.difficulty === '易'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-slate-100 text-slate-600',
                  ]"
                >
                  {{ q.difficulty || '-' }}
                </span>
              </td>
              <td class="px-3 py-3 text-xs text-slate-500">
                {{ q.source_page || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        class="px-3 py-2 border-t border-slate-100 flex items-center justify-between"
      >
        <span class="text-xs text-slate-400"
          >共 {{ allQuestions.length }} 道题目</span
        >
        <div v-if="totalPages > 1" class="flex items-center gap-1">
          <button
            :disabled="page <= 1"
            :class="[
              'px-2 py-1 text-xs rounded',
              page <= 1
                ? 'text-slate-300 cursor-not-allowed'
                : 'text-slate-600 hover:bg-slate-100',
            ]"
            @click="setPage(page - 1)"
          >
            ‹
          </button>
          <button
            v-for="idx in Math.min(5, totalPages)"
            :key="idx"
            :class="[
              'px-2 py-1 text-xs rounded',
              page === Math.max(1, Math.min(totalPages, page - 2 + idx))
                ? 'bg-brand-500 text-white'
                : 'text-slate-600 hover:bg-slate-100',
            ]"
            @click="setPage(Math.max(1, Math.min(totalPages, page - 2 + idx)))"
          >
            {{ Math.max(1, Math.min(totalPages, page - 2 + idx)) }}
          </button>
          <button
            :disabled="page >= totalPages"
            :class="[
              'px-2 py-1 text-xs rounded',
              page >= totalPages
                ? 'text-slate-300 cursor-not-allowed'
                : 'text-slate-600 hover:bg-slate-100',
            ]"
            @click="setPage(page + 1)"
          >
            ›
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
