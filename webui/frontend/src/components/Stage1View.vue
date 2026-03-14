<script setup lang="ts">
import { computed } from 'vue';
import { usePipelineStore } from '@/stores/pipeline';
import BarChartHorizontal from './charts/BarChartHorizontal.vue';
import DoughnutChart from './charts/DoughnutChart.vue';

const store = usePipelineStore();
const stats = computed(() => store.stage1Stats);
const pairs = computed(() => store.filteredStage1Pairs);
const getPairCategories = (p: { subcategories?: string[] }) =>
  store.getPairCategories(p as import('@/types/pipeline').Stage1Pair);

function toggleSort(key: 'page' | 'count') {
  if (store.stage1SortKey === key) {
    store.stage1SortAsc = !store.stage1SortAsc;
  } else {
    store.stage1SortKey = key;
    store.stage1SortAsc = true;
  }
}

const pieColors = [
  '#3B82F6',
  '#F59E0B',
  '#10B981',
  '#8B5CF6',
  '#EC4899',
  '#06B6D4',
  '#84CC16',
  '#F97316',
  '#6366F1',
  '#94A3B8',
];

const catEntries = computed(() =>
  (stats.value?.catList || []).map((k) => ({
    name: k,
    count: (stats.value?.catDist || {})[k] || 0,
  }))
);

const catPieEntries = computed(() => {
  const entries = catEntries.value;
  if (entries.length <= 10) return entries;
  const rest = entries.slice(9);
  return [
    ...entries.slice(0, 9),
    { name: '其他', count: rest.reduce((s, e) => s + e.count, 0) },
  ];
});

const subcatEntries = computed(() => {
  const list = stats.value?.subcatList || [];
  const dist = stats.value?.subcatDist || {};
  return list
    .map((k) => ({ name: k, count: dist[k] }))
    .sort((a, b) => b.count - a.count);
});

const subcatBarEntries = computed(() => subcatEntries.value.slice(0, 20));

const subcatPieEntries = computed(() => {
  const entries = subcatEntries.value;
  if (entries.length <= 10) return entries;
  const rest = entries.slice(9);
  return [
    ...entries.slice(0, 9),
    { name: '其他', count: rest.reduce((s, e) => s + e.count, 0) },
  ];
});
</script>

<template>
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-5">
    <section class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div
        v-for="(c, i) in [
          { label: '总页数', value: stats?.totalPages ?? 0, icon: 'file', accent: 'blue' },
          {
            label: '总分组数',
            value: stats?.totalPairs ?? 0,
            icon: 'grid',
            accent: 'indigo',
          },
          {
            label: '知识小类数',
            value: stats?.subcatCount ?? 0,
            icon: 'tag',
            accent: 'amber',
          },
          {
            label: '空分组数',
            value: stats?.emptyPairs ?? 0,
            sub: '未标注小类',
            icon: 'pie',
            accent: 'emerald',
          },
        ]"
        :key="c.label"
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
        :style="{ animationDelay: `${0.05 * (i + 1)}s` }"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-xs font-medium text-slate-500">{{ c.label }}</p>
            <p class="text-2xl font-bold text-slate-900 mt-1">{{ c.value }}</p>
            <p v-if="c.sub" class="text-xs text-slate-400 mt-0.5">{{ c.sub }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col min-h-0"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          知识大类分布
        </h3>
        <div
          v-if="catEntries.length"
          class="flex-1 min-h-[360px] flex items-center justify-center w-full"
        >
          <div class="w-full h-[360px]">
            <BarChartHorizontal
              :labels="catEntries.map((e) => (e.name.length > 10 ? e.name.slice(0, 10) + '...' : e.name))"
              :data="catEntries.map((e) => e.count)"
              border-color="#10B981"
              background-color="#10B98120"
            />
          </div>
        </div>
      </div>
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col min-h-0"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          知识大类占比
        </h3>
        <div
          class="flex-1 min-h-[280px] flex flex-col items-center justify-center gap-4"
        >
          <div
            v-if="catPieEntries.length"
            class="h-[220px] w-[200px] flex items-center justify-center"
          >
            <DoughnutChart
              :labels="catPieEntries.map((e) => e.name)"
              :data="catPieEntries.map((e) => e.count)"
              :colors="pieColors"
            />
          </div>
          <div class="w-full space-y-2 text-xs min-w-0">
            <div
              v-for="(e, i) in catPieEntries"
              :key="e.name"
              class="flex items-center justify-between gap-3"
            >
              <span class="flex items-center gap-2 min-w-0">
                <span
                  class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  :style="{ background: pieColors[i % pieColors.length] }"
                />
                <span class="text-slate-600 truncate">{{ e.name }}</span>
              </span>
              <span class="font-medium text-slate-800 flex-shrink-0">
                {{ e.count }}
                ({{
                  catPieEntries.reduce((s, x) => s + x.count, 0)
                    ? ((e.count / catPieEntries.reduce((s, x) => s + x.count, 0)) * 100).toFixed(
                        1
                      )
                    : 0
                }}%)
              </span>
            </div>
            <div v-if="!catPieEntries.length" class="text-slate-400 text-xs">
              暂无数据
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col min-h-0"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          知识小类分布
        </h3>
        <div
          v-if="subcatBarEntries.length"
          class="flex-1 min-h-[500px] flex items-center justify-center w-full"
        >
          <div class="w-full h-[500px]">
            <BarChartHorizontal
              :labels="
                subcatBarEntries.map((e) =>
                  e.name.length > 10 ? e.name.slice(0, 10) + '...' : e.name
                )
              "
              :data="subcatBarEntries.map((e) => e.count)"
              border-color="#3B82F6"
              background-color="#3B82F620"
            />
          </div>
        </div>
      </div>
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up flex flex-col min-h-0"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4 flex-shrink-0">
          知识小类占比
        </h3>
        <div
          class="flex-1 min-h-[280px] flex flex-col items-center justify-center gap-4"
        >
          <div
            v-if="subcatPieEntries.length"
            class="h-[220px] w-[200px] flex items-center justify-center"
          >
            <DoughnutChart
              :labels="subcatPieEntries.map((e) => e.name)"
              :data="subcatPieEntries.map((e) => e.count)"
              :colors="pieColors"
            />
          </div>
          <div class="w-full space-y-2 text-xs min-w-0">
            <div
              v-for="(e, i) in subcatPieEntries"
              :key="e.name"
              class="flex items-center justify-between gap-3"
            >
              <span class="flex items-center gap-2 min-w-0">
                <span
                  class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  :style="{ background: pieColors[i % pieColors.length] }"
                />
                <span class="text-slate-600 truncate">{{ e.name }}</span>
              </span>
              <span class="font-medium text-slate-800 flex-shrink-0">
                {{ e.count }}
                ({{
                  subcatPieEntries.reduce((s, x) => s + x.count, 0)
                    ? (
                        (e.count /
                          subcatPieEntries.reduce((s, x) => s + x.count, 0)) *
                        100
                      ).toFixed(1)
                    : 0
                }}%)
              </span>
            </div>
            <div v-if="!subcatPieEntries.length" class="text-slate-400 text-xs">
              暂无数据
            </div>
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
        <h3 class="text-sm font-semibold text-slate-800">分组详情</h3>
        <div class="flex items-center gap-2 w-full sm:w-auto">
          <div class="relative flex-1 sm:flex-initial">
            <svg
              class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              v-model="store.stage1Search"
              type="search"
              placeholder="搜索页码、大类或小类..."
              class="w-full sm:w-52 pl-8 pr-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400"
            />
          </div>
          <select
            v-model="store.stage1CatFilter"
            class="px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">全部大类</option>
            <option v-for="c in stats?.catList" :key="c" :value="c">
              {{ c }}
            </option>
          </select>
          <select
            v-model="store.stage1SubcatFilter"
            class="px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">全部小类</option>
            <option v-for="s in stats?.subcatList" :key="s" :value="s">
              {{ s }}
            </option>
          </select>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50/60 border-b border-slate-100">
              <th
                class="px-3 py-2 text-xs font-semibold text-slate-500 w-10 text-center"
              >
                #
              </th>
              <th
                class="px-3 py-2 text-xs font-semibold text-slate-500 w-20 cursor-pointer"
                @click="toggleSort('page')"
              >
                页码
                <span v-if="store.stage1SortKey === 'page'">
                  {{ store.stage1SortAsc ? '▲' : '▼' }}
                </span>
              </th>
              <th
                class="px-3 py-2 text-xs font-semibold text-slate-500 min-w-[140px]"
              >
                知识大类
              </th>
              <th
                class="px-3 py-2 text-xs font-semibold text-slate-500 w-16 text-center cursor-pointer"
                @click="toggleSort('count')"
              >
                小类数
                <span v-if="store.stage1SortKey === 'count'">
                  {{ store.stage1SortAsc ? '▲' : '▼' }}
                </span>
              </th>
              <th
                class="px-3 py-2 text-xs font-semibold text-slate-500 min-w-[200px]"
              >
                知识小类
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-if="!pairs.length"
              class="border-b border-slate-50"
            >
              <td
                colspan="5"
                class="px-4 py-10 text-center text-sm text-slate-400"
              >
                无匹配数据
              </td>
            </tr>
            <tr
              v-for="(p, i) in pairs"
              :key="i"
              class="border-b border-slate-50 hover:bg-slate-50/60 transition-colors"
            >
              <td class="px-3 py-2.5 text-xs text-slate-400 text-center">
                {{ i + 1 }}
              </td>
              <td class="px-3 py-2.5 text-sm font-semibold text-slate-800">
                {{ p.page_info || '-' }}
              </td>
              <td class="px-3 py-2.5 text-sm text-slate-600">
                {{ getPairCategories(p).join('、') || '-' }}
              </td>
              <td class="px-3 py-2.5 text-sm text-center text-slate-600">
                {{ (p.subcategories || []).length }}
              </td>
              <td class="px-3 py-2.5 text-sm text-slate-600">
                {{ (p.subcategories || []).join('、') || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="px-3 py-2 border-t border-slate-100">
        <span class="text-xs text-slate-400">共 {{ pairs.length }} 组</span>
      </div>
    </section>
  </main>
</template>
