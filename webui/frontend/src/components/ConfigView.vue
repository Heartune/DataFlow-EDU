<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useConfigStore } from '@/stores/config';
import { listPresets } from '@/api/config';
import { useToastStore } from '@/stores/toast';
import DoughnutChart from '@/components/charts/DoughnutChart.vue';
import type { TaxonomyItem, AbilityLevelItem } from '@/types/config';

const configStore = useConfigStore();
const toastStore = useToastStore();

const presets = ref<string[]>([]);
const selectedPreset = ref('');
const activeSection = ref<'taxonomy' | 'questions' | 'ability' | 'operators'>('taxonomy');
const operatorTab = ref('mineru_ocr');

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

const operatorLabels: Record<string, string> = {
  mineru_ocr: '1.2 MinerU OCR',
  generation: '2.1 Generation',
  balancing: '2.2 Balancing',
  ambiguity_cleaning: '3.1 Ambiguity Cleaning',
  ambiguity_refinement: '3.2 Ambiguity Refinement',
  domain_cleaning: '3.3 Domain Cleaning',
  domain_refinement: '3.4 Domain Refinement',
  deduplication: '3.5 Deduplication',
  execute: '4.1 Execute',
  judge: '4.2 Judge',
};

const config = computed(() => configStore.config);

const questionPieData = computed(() => {
  const qs = config.value.question_types || [];
  return {
    labels: qs.map((q) => q.name),
    data: qs.map((q) => q.weight),
  };
});

const abilityPieData = computed(() => {
  const ab = config.value.ability_levels || [];
  return {
    labels: ab.map((a) => a.name),
    data: ab.map((a) => a.weight),
  };
});

onMounted(async () => {
  presets.value = await listPresets();
  await configStore.load();
});

async function handleLoadPreset() {
  if (!selectedPreset.value) return;
  const ok = await configStore.loadPresetConfig(selectedPreset.value);
  if (ok) toastStore.show('已加载预设', 'success');
}

async function handleSave() {
  const ok = await configStore.save();
  if (ok) toastStore.show('配置已保存', 'success');
}

function addTaxonomy() {
  config.value.taxonomy.push({ name: '', subcategories: [] });
}

function removeTaxonomy(i: number) {
  config.value.taxonomy.splice(i, 1);
}

function addSubcategory(t: TaxonomyItem) {
  t.subcategories.push('');
}

function removeSubcategory(t: TaxonomyItem, j: number) {
  t.subcategories.splice(j, 1);
}

function addQuestionType() {
  config.value.question_types.push({ name: '', weight: 0.25 });
}

function removeQuestionType(i: number) {
  config.value.question_types.splice(i, 1);
}

function addAbilityLevel() {
  config.value.ability_levels.push({
    name: '',
    weight: 0.25,
    description: '',
    sublevels: [],
  });
}

function removeAbilityLevel(i: number) {
  config.value.ability_levels.splice(i, 1);
}

function addSublevel(a: AbilityLevelItem) {
  a.sublevels.push('');
}

function removeSublevel(a: AbilityLevelItem, j: number) {
  a.sublevels.splice(j, 1);
}

function opValue(op: Record<string, unknown>, key: string): string | number | boolean {
  const v = op[key];
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v;
  return String(v ?? '');
}

</script>

<template>
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-5">
    <section
      class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
    >
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2">
          <select
            v-model="selectedPreset"
            class="px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 bg-white cursor-pointer"
          >
            <option value="">选择预设</option>
            <option v-for="p in presets" :key="p" :value="p">{{ p }}</option>
          </select>
          <button
            type="button"
            class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50"
            @click="handleLoadPreset"
          >
            加载预设
          </button>
        </div>
        <button
          :disabled="configStore.saving"
          class="px-4 py-1.5 rounded-lg bg-brand-500 text-white text-xs font-medium hover:bg-brand-600 disabled:opacity-70"
          @click="handleSave"
        >
          {{ configStore.saving ? '保存中...' : '保存配置' }}
        </button>
      </div>
      <div
        v-if="configStore.errors.length"
        class="mt-3 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700"
      >
        <ul class="list-disc list-inside space-y-1">
          <li v-for="(e, i) in configStore.errors" :key="i">{{ e }}</li>
        </ul>
      </div>
    </section>

    <section class="flex gap-2">
      <button
        v-for="s in [
          { id: 'taxonomy', label: '考察知识方向' },
          { id: 'questions', label: '题型池' },
          { id: 'ability', label: '能力层级' },
          { id: 'operators', label: 'Operator 参数' },
        ]"
        :key="s.id"
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          activeSection === s.id
            ? 'bg-brand-500 text-white'
            : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
        ]"
        @click="activeSection = s.id as typeof activeSection"
      >
        {{ s.label }}
      </button>
    </section>

    <!-- Taxonomy -->
    <section
      v-show="activeSection === 'taxonomy'"
      class="grid grid-cols-1 lg:grid-cols-2 gap-4 animate-fade-in-up"
    >
      <div
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4">编辑</h3>
        <div class="space-y-3">
          <div
            v-for="(t, i) in config.taxonomy"
            :key="i"
            class="border border-slate-100 rounded-lg p-3"
          >
            <div class="flex items-center gap-2 mb-2">
              <input
                v-model="t.name"
                type="text"
                placeholder="大类名称"
                class="flex-1 px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs"
              />
              <button
                type="button"
                class="px-2 py-1 text-red-600 hover:bg-red-50 rounded"
                @click="removeTaxonomy(i)"
              >
                删除
              </button>
            </div>
            <div class="space-y-1.5 ml-3">
              <div
                v-for="(_s, j) in t.subcategories"
                :key="j"
                class="flex items-center gap-2"
              >
                <input
                  v-model="t.subcategories[j]"
                  type="text"
                  placeholder="小类"
                  class="flex-1 px-2.5 py-1 border border-slate-200 rounded text-xs"
                />
                <button
                  type="button"
                  class="px-1.5 text-red-500 hover:bg-red-50"
                  @click="removeSubcategory(t, j)"
                >
                  ×
                </button>
              </div>
              <button
                type="button"
                class="text-xs text-brand-600 hover:underline"
                @click="addSubcategory(t)"
              >
                + 添加小类
              </button>
            </div>
          </div>
          <button
            type="button"
            class="text-sm text-brand-600 hover:underline"
            @click="addTaxonomy"
          >
            + 添加大类
          </button>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">树形预览</h3>
        <div class="space-y-2 text-sm">
          <div
            v-for="(t, i) in config.taxonomy"
            :key="i"
            class="border-l-2 border-brand-200 pl-3"
          >
            <span class="font-medium text-slate-800">{{ t.name || '(未命名)' }}</span>
            <div class="mt-1 space-y-0.5 text-slate-600">
              <span v-for="(sub, j) in t.subcategories" :key="j" class="block ml-2">
                · {{ sub || '(未命名)' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Question types -->
    <section
      v-show="activeSection === 'questions'"
      class="grid grid-cols-1 lg:grid-cols-2 gap-4 animate-fade-in-up"
    >
      <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">编辑</h3>
        <div class="space-y-2">
          <div
            v-for="(q, i) in config.question_types"
            :key="i"
            class="flex items-center gap-2"
          >
            <input
              v-model="q.name"
              type="text"
              placeholder="题型"
              class="flex-1 px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs"
            />
            <input
              v-model.number="q.weight"
              type="number"
              step="0.01"
              min="0"
              max="1"
              class="w-20 px-2 py-1.5 border border-slate-200 rounded text-xs"
            />
            <button
              type="button"
              class="px-2 text-red-600"
              @click="removeQuestionType(i)"
            >
              删除
            </button>
          </div>
          <button
            type="button"
            class="text-sm text-brand-600 hover:underline"
            @click="addQuestionType"
          >
            + 添加题型
          </button>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">权重占比</h3>
        <div
          v-if="questionPieData.labels.length"
          class="h-[220px] w-[200px] mx-auto"
        >
          <DoughnutChart
            :labels="questionPieData.labels"
            :data="questionPieData.data"
            :colors="pieColors"
          />
        </div>
        <div class="mt-3 space-y-1 text-xs text-slate-600">
          <div
            v-for="(q, i) in config.question_types"
            :key="i"
            class="flex justify-between"
          >
            <span>{{ q.name || '(未命名)' }}</span>
            <span>{{ ((q.weight || 0) * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Ability levels -->
    <section
      v-show="activeSection === 'ability'"
      class="grid grid-cols-1 lg:grid-cols-2 gap-4 animate-fade-in-up"
    >
      <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">编辑</h3>
        <div class="space-y-3 max-h-[500px] overflow-y-auto">
          <div
            v-for="(a, i) in config.ability_levels"
            :key="i"
            class="border border-slate-100 rounded-lg p-3"
          >
            <input
              v-model="a.name"
              type="text"
              placeholder="能力层级"
              class="w-full px-2.5 py-1.5 border border-slate-200 rounded text-xs mb-2"
            />
            <input
              v-model="a.description"
              type="text"
              placeholder="描述"
              class="w-full px-2.5 py-1 border border-slate-200 rounded text-xs mb-2"
            />
            <div class="flex items-center gap-2 mb-2">
              <input
                v-model.number="a.weight"
                type="number"
                step="0.01"
                min="0"
                max="1"
                class="w-20 px-2 py-1 border border-slate-200 rounded text-xs"
              />
              <button
                type="button"
                class="text-red-600 text-xs"
                @click="removeAbilityLevel(i)"
              >
                删除
              </button>
            </div>
            <div class="space-y-1 ml-2">
              <div
                v-for="(_s, j) in a.sublevels"
                :key="j"
                class="flex gap-2"
              >
                <input
                  v-model="a.sublevels[j]"
                  type="text"
                  placeholder="子层级"
                  class="flex-1 px-2 py-1 border rounded text-xs"
                />
                <button
                  type="button"
                  class="text-red-500"
                  @click="removeSublevel(a, j)"
                >
                  ×
                </button>
              </div>
              <button
                type="button"
                class="text-xs text-brand-600"
                @click="addSublevel(a)"
              >
                + 子层级
              </button>
            </div>
          </div>
          <button
            type="button"
            class="text-sm text-brand-600 hover:underline"
            @click="addAbilityLevel"
          >
            + 添加能力层级
          </button>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5">
        <h3 class="text-sm font-semibold text-slate-800 mb-4">预览</h3>
        <div
          v-if="abilityPieData.labels.length"
          class="h-[180px] w-[180px] mx-auto"
        >
          <DoughnutChart
            :labels="abilityPieData.labels"
            :data="abilityPieData.data"
            :colors="pieColors"
          />
        </div>
        <div class="mt-4 space-y-2 text-sm">
          <div
            v-for="(a, i) in config.ability_levels"
            :key="i"
            class="border-l-2 border-slate-200 pl-3"
          >
            <span class="font-medium">{{ a.name || '(未命名)' }}</span>
            <span class="text-slate-500 text-xs ml-1">({{ (a.weight * 100).toFixed(0) }}%)</span>
            <div class="text-slate-600 text-xs mt-0.5">
              {{ a.sublevels.join('、') || '—' }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Operators -->
    <section v-show="activeSection === 'operators'" class="animate-fade-in-up">
      <div class="flex flex-wrap gap-1 mb-4">
        <button
          v-for="(label, key) in operatorLabels"
          :key="key"
          :class="[
            'px-3 py-1.5 rounded-lg text-xs font-medium',
            operatorTab === key
              ? 'bg-brand-500 text-white'
              : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
          ]"
          @click="operatorTab = key"
        >
          {{ label }}
        </button>
      </div>
      <div
        v-for="(op, opKey) in config.operators"
        v-show="operatorTab === opKey"
        :key="opKey"
        class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5"
      >
        <h3 class="text-sm font-semibold text-slate-800 mb-4">
          {{ operatorLabels[opKey] || opKey }}
        </h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div
            v-for="key in Object.keys(op).sort()"
            :key="key"
            class="flex flex-col gap-1"
          >
            <label class="text-xs text-slate-500">{{ key }}</label>
            <input
              v-if="typeof op[key] === 'boolean'"
              type="checkbox"
              :checked="!!op[key]"
              class="w-4 h-4"
              @change="op[key] = ($event.target as HTMLInputElement).checked"
            />
            <input
              v-else
              :value="opValue(op, key)"
              type="text"
              class="px-2.5 py-1.5 border border-slate-200 rounded text-xs"
              @input="
                (e) => {
                  const v = (e.target as HTMLInputElement).value;
                  if (v === 'true') op[key] = true;
                  else if (v === 'false') op[key] = false;
                  else if (!isNaN(Number(v))) op[key] = Number(v);
                  else op[key] = v;
                }
              "
            />
          </div>
        </div>
        <div
          v-if="Array.isArray(op.excluded_ability_sublevels) || Array.isArray(op.target_scores)"
          class="mt-3"
        >
          <template v-if="op.excluded_ability_sublevels">
            <label class="text-xs text-slate-500 block mb-1">excluded_ability_sublevels</label>
            <input
              :value="(op.excluded_ability_sublevels as string[]).join(', ')"
              type="text"
              placeholder="逗号分隔"
              class="w-full px-2.5 py-1.5 border border-slate-200 rounded text-xs"
              @input="
                op.excluded_ability_sublevels = (($event.target as HTMLInputElement).value || '')
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean);
              "
            />
          </template>
          <template v-if="op.target_scores">
            <label class="text-xs text-slate-500 block mb-1 mt-2">target_scores</label>
            <input
              :value="(op.target_scores as number[]).join(', ')"
              type="text"
              placeholder="如 2, 3"
              class="w-full px-2.5 py-1.5 border border-slate-200 rounded text-xs"
              @input="
                op.target_scores = (($event.target as HTMLInputElement).value || '')
                  .split(',')
                  .map((s) => parseInt(s.trim(), 10))
                  .filter((n) => !isNaN(n));
              "
            />
          </template>
        </div>
      </div>
    </section>
  </main>
</template>
