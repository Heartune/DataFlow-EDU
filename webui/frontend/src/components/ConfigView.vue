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
/** 当前展开的阶段（多算子阶段点击后展开） */
const expandedStage = ref<string | null>(null);

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

/** Pipeline 按阶段分组 */
const operatorStages: { label: string; color: string; ops: string[] }[] = [
  { label: '数据准备', color: 'blue', ops: ['mineru_ocr'] },
  { label: '生成均衡', color: 'green', ops: ['generation', 'balancing'] },
  {
    label: '清洗精修',
    color: 'amber',
    ops: [
      'ambiguity_cleaning',
      'ambiguity_refinement',
      'domain_cleaning',
      'domain_refinement',
      'deduplication',
    ],
  },
  { label: '执行评测', color: 'violet', ops: ['execute', 'judge'] },
];

/** 中英对照 + 简单描述 */
const paramMeta: Record<string, Record<string, { label: string; desc: string }>> = {
  mineru_ocr: {
    batch_size: { label: '每批数量 (batch_size)', desc: '每批提交图片数量' },
    poll_interval: { label: '轮询间隔秒 (poll_interval)', desc: '轮询 MinerU 任务状态的间隔' },
    poll_timeout: { label: '轮询超时秒 (poll_timeout)', desc: '轮询超时时间' },
    skip_existing: { label: '跳过已有 (skip_existing)', desc: '是否跳过已有 .md 的图片' },
    language: { label: '语言 (language)', desc: 'OCR 语言 ch/en' },
    enable_formula: { label: '公式识别 (enable_formula)', desc: '是否启用公式识别' },
    enable_table: { label: '表格识别 (enable_table)', desc: '是否启用表格识别' },
    img_dir: { label: '图片目录 (img_dir)', desc: '教材图片根目录' },
    md_dir: { label: '输出目录 (md_dir)', desc: '输出 Markdown 根目录' },
  },
  generation: {
    md_dir: { label: '输入目录 (md_dir)', desc: 'MinerU 输出的 Markdown 根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '生成题目输出根目录' },
    questions_per_pair: { label: '每对页题数 (questions_per_pair)', desc: '每两页生成的题目数' },
    max_workers: { label: '最大并发 (max_workers)', desc: '并行请求数' },
    api_delay: { label: 'API 延迟秒 (api_delay)', desc: '请求间延迟' },
    request_timeout: { label: '请求超时秒 (request_timeout)', desc: '单次请求超时' },
    max_retries: { label: '最大重试 (max_retries)', desc: '失败重试次数' },
    save_interval: { label: '保存间隔 (save_interval)', desc: '每隔多少轮保存一次' },
  },
  balancing: {
    output_dir: { label: '输出目录 (output_dir)', desc: '均衡后输出根目录' },
    sample_size: { label: '采样数 (sample_size)', desc: '每轮采样题目数' },
    max_iterations: { label: '最大迭代 (max_iterations)', desc: '均衡最大迭代轮数' },
    questions_per_round: { label: '每轮题数 (questions_per_round)', desc: '每轮生成题目数' },
    max_per_sublevel_iterations: { label: '子层迭代 (max_per_sublevel_iterations)', desc: '每个子层最大迭代次数' },
    tolerance: { label: '容差 (tolerance)', desc: '分布偏离容忍度' },
    excluded_ability_sublevels: { label: '排除子层 (excluded_ability_sublevels)', desc: '不参与均衡的能力子层' },
  },
  ambiguity_cleaning: {
    output_dir: { label: '输出目录 (output_dir)', desc: '清洗后输出根目录' },
    input_dir: { label: '输入目录 (input_dir)', desc: '待清洗题目根目录' },
    max_workers: { label: '最大并发 (max_workers)', desc: '并行请求数' },
    max_retries: { label: '最大重试 (max_retries)', desc: '失败重试次数' },
    threshold_remove: { label: '剔除阈值 (threshold_remove)', desc: '评分≤此值剔除' },
  },
  ambiguity_refinement: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待精修题目根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '精修后输出根目录' },
    max_workers: { label: '最大并发 (max_workers)', desc: '并行请求数' },
    max_retries: { label: '最大重试 (max_retries)', desc: '失败重试次数' },
    target_scores: { label: '目标分数 (target_scores)', desc: '需 LLM 精修的分数段' },
    threshold_discard: { label: '丢弃阈值 (threshold_discard)', desc: '精修后≤此分丢弃' },
  },
  domain_cleaning: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待领域清洗根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '清洗后输出根目录' },
    max_workers: { label: '最大并发 (max_workers)', desc: '并行请求数' },
    max_retries: { label: '最大重试 (max_retries)', desc: '失败重试次数' },
    threshold_remove: { label: '剔除阈值 (threshold_remove)', desc: '评分≤此值剔除' },
    domain_name: { label: '领域名 (domain_name)', desc: '学科/领域名称' },
  },
  domain_refinement: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待领域精修根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '精修后输出根目录' },
    max_workers: { label: '最大并发 (max_workers)', desc: '并行请求数' },
    max_retries: { label: '最大重试 (max_retries)', desc: '失败重试次数' },
    target_scores: { label: '目标分数 (target_scores)', desc: '需 LLM 精修的分数段' },
    threshold_discard: { label: '丢弃阈值 (threshold_discard)', desc: '精修后≤此分丢弃' },
    domain_name: { label: '领域名 (domain_name)', desc: '学科/领域名称' },
  },
  deduplication: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待去重根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '去重后输出根目录' },
    threshold: { label: '相似度阈值 (threshold)', desc: 'MinHash 相似度阈值' },
    num_perm: { label: '排列数 (num_perm)', desc: 'MinHash 排列数' },
    n_gram: { label: 'N-gram 大小 (n_gram)', desc: '字符级 n-gram 大小' },
  },
  execute: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待执行题目根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '执行结果输出根目录' },
  },
  judge: {
    input_dir: { label: '输入目录 (input_dir)', desc: '待评测题目根目录' },
    output_dir: { label: '输出目录 (output_dir)', desc: '评测结果输出根目录' },
  },
};

function getParamLabel(opKey: string, key: string): string {
  return paramMeta[opKey]?.[key]?.label ?? key;
}

function getParamDesc(opKey: string, key: string): string {
  return paramMeta[opKey]?.[key]?.desc ?? '';
}

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

function autoResizeTextarea(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

</script>

<template>
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-5">
    <section
      class="bg-white rounded-xl shadow-sm border border-slate-200/60 p-5 animate-fade-in-up"
    >
      <p class="text-slate-600 text-sm mb-4 leading-relaxed">
        欢迎来到DataFlow-EDU参数配置面板（Configuration Manager）！<br>
        该面板用于管理「考察知识方向」「能力层级」「题型池」及各 Pipeline 算子的参数。<br>
        选择预设可快速加载学科模板（如 biology），编辑后请点击「保存配置」生效。<br>
        下方四个标签分别对应知识分类、题型权重、能力层级与算子参数的配置。
      </p>
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
      class="space-y-3 animate-fade-in-up"
    >
      <div class="text-slate-600 text-sm space-y-2 leading-relaxed">
        <p><strong>【考察知识方向】的参数配置</strong>解决【考什么】的问题。<br>
        您需要这里定义学科的大类-小类双层架构（如生物学科下分细胞、遗传等，细胞下分功能、结构、生命活动等），建议与教材的章节目录或课标知识结构相对应。<br>
        在题目生成阶段，系统会先按您配置的方向，对每段教材内容做知识分类，再生成题目，从而从<strong>知识覆盖</strong>维度控制题目分布。<br>
        后续在 Execute & Judge 阶段，也可以按知识方向统计模型得分，把握模型对不同知识方向的掌握程度。</p>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
        <div class="space-y-2">
          <div
            v-for="(t, i) in config.taxonomy"
            :key="i"
            class="rounded-lg border border-slate-100 bg-slate-50/40 overflow-hidden hover:border-slate-200/60 transition-colors"
          >
            <div class="flex items-center gap-2 px-3 py-2.5 border-l-2 border-brand-400 bg-white/60">
              <span
                class="flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center text-[11px] font-semibold text-white bg-brand-500"
              >
                {{ i + 1 }}
              </span>
              <span class="font-semibold text-slate-800 text-sm">{{ t.name || '(未命名)' }}</span>
            </div>
            <div
              v-if="t.subcategories?.length"
              class="py-2 px-3 space-y-1"
            >
              <div
                v-for="(sub, j) in t.subcategories"
                :key="j"
                class="flex items-center gap-2 pl-6 text-sm text-slate-600"
              >
                <span class="flex-shrink-0 w-1 h-1 rounded-full bg-brand-300" aria-hidden />
                <span>{{ sub || '(未命名)' }}</span>
              </div>
            </div>
            <div
              v-else
              class="py-2 px-3 pl-6 text-xs text-slate-400"
            >
              —
            </div>
          </div>
        </div>
      </div>
      </div>
    </section>

    <!-- Question types -->
    <section
      v-show="activeSection === 'questions'"
      class="space-y-3 animate-fade-in-up"
    >
      <div class="text-slate-600 text-sm space-y-2 leading-relaxed">
        <p><strong>【题型池的参数配置】</strong>决定了我们的【考察形式】，即题目以何种方式呈现（选择题、填空题、简答题等）。<br>不同题型考察的作答方式不同，建议设置多种题型并控制权重分布均衡，单一题型堆砌可能会导致 Benchmark 偏颇。<br>
        在此配置各题型及其权重后，题目生成阶段会按权重比例分配题型，使生成的题目在<strong>题型分布</strong>上可控；<br>在评测时，也能从作答形式维度分析模型在不同题型上的表现，使评估更全面。</p>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
      </div>
    </section>

    <!-- Ability levels -->
    <section
      v-show="activeSection === 'ability'"
      class="space-y-3 animate-fade-in-up"
    >
      <div class="text-slate-600 text-sm space-y-2 leading-relaxed">
        <p><strong>【能力层级的参数配置】</strong>受教育心理学中常用的“布鲁姆认知目标分类”框架启发，我们通过<strong>模型能力（即核心素养）</strong>的角度控制生成题目的分布，并对模型进行相应评估。<br>
        这里按照采用「主层级-子层级」双层架构，按认知/思维层次划分（例如常见的记忆、理解、应用、分析等，可自定义名称与子类）。<br>
        在为各层级设置权重后，题目生成阶段会基于随机槽机制和题目均衡算子控制题目的能力层级分布。<br>
        评测时则可按能力层级统计得分，得到模型在记忆、理解、应用、分析等维度的精细化能力素养图谱。</p>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
            <textarea
              v-model="a.description"
              placeholder="描述"
              rows="2"
              class="w-full px-2.5 py-1 border border-slate-200 rounded text-xs mb-2 resize-none overflow-hidden min-h-[28px]"
              @input="autoResizeTextarea"
              @focus="autoResizeTextarea"
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
      </div>
    </section>

    <!-- Operators -->
    <section v-show="activeSection === 'operators'" class="animate-fade-in-up space-y-4">
      <div class="text-slate-600 text-sm space-y-2 leading-relaxed">
        <p><strong>【算子参数配置】</strong>我们的 Pipeline 包括「数据准备 → 生成均衡 → 清洗精修 → 执行评测」各阶段，都由具体算子执行。<br>每个算子有各自的运行参数（如目录路径、并发数、超时等），支持您通过交互式的方式，根据需要灵活配置，使得整套系统有效适应您的个性化需求。<br>
        具体来说，此处集中配置 MinerU OCR、Generation、Balancing、各类清洗/精修算子以及 Execute、Judge 等的参数。<br>
        您无需修改代码或YAML参数文件，只需修改后点击【保存配置】。后续在执行对应阶段时，系统会自动读取这些配置。</p>
      </div>
      <!-- Pipeline: 一行，默认 1.2，点击阶段展开算子 -->
      <div class="flex flex-nowrap items-center overflow-x-auto pb-2 mb-4">
        <template v-for="(stage, sIdx) in operatorStages" :key="stage.label">
          <span
            v-if="sIdx > 0"
            class="flex-shrink-0 mx-0.5 text-slate-300"
            aria-hidden="true"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </span>
          <!-- 单算子阶段：直接展示 -->
          <template v-if="stage.ops.length === 1">
            <button
              :class="[
                'flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
                operatorTab === stage.ops[0]
                  ? 'bg-brand-500 text-white'
                  : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
              ]"
              @click="operatorTab = stage.ops[0]"
            >
              {{ operatorLabels[stage.ops[0]] }}
            </button>
          </template>
          <!-- 多算子阶段：纯 CSS 展开/收起动效 -->
          <div
            v-else
            class="stage-pipeline-cell"
            :class="{ 'stage-pipeline-cell--expanded': expandedStage === stage.label }"
          >
            <button
              :class="[
                'stage-pipeline-cell__collapsed flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all duration-300',
                stage.color === 'green' && 'border-emerald-200 bg-emerald-50/80 text-emerald-700 hover:bg-emerald-100/80',
                stage.color === 'amber' && 'border-amber-200 bg-amber-50/80 text-amber-700 hover:bg-amber-100/80',
                stage.color === 'violet' && 'border-violet-200 bg-violet-50/80 text-violet-700 hover:bg-violet-100/80',
              ]"
              @click="expandedStage = stage.label"
            >
              {{ stage.label }}
              <svg class="inline-block w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <div class="stage-pipeline-cell__expanded flex flex-shrink-0 items-center gap-0.5">
              <template v-for="(key, opIdx) in stage.ops" :key="key">
                <span
                  v-if="opIdx > 0"
                  class="flex-shrink-0 text-slate-300"
                  aria-hidden="true"
                >
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                </span>
                <button
                  :class="[
                    'flex-shrink-0 px-2.5 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all',
                    operatorTab === key ? 'bg-brand-500 text-white' : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
                  ]"
                  @click="operatorTab = key"
                >
                  {{ operatorLabels[key] }}
                </button>
              </template>
              <button
                type="button"
                class="flex-shrink-0 p-1 rounded text-slate-400 hover:bg-slate-100"
                title="收起"
                @click="expandedStage = null"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
            </div>
          </div>
        </template>
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
            <div>
              <label class="text-xs text-slate-500">{{ getParamLabel(opKey, key) }}</label>
              <p v-if="getParamDesc(opKey, key)" class="text-[10px] text-slate-400 mt-0.5">
                {{ getParamDesc(opKey, key) }}
              </p>
            </div>
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
            <label class="text-xs text-slate-500 block mb-1">{{ getParamLabel(opKey, 'excluded_ability_sublevels') }}</label>
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
            <label class="text-xs text-slate-500 block mb-1 mt-2">{{ getParamLabel(opKey, 'target_scores') }}</label>
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

<style scoped>
.stage-pipeline-cell {
  display: inline-flex;
  position: relative;
  align-items: center;
  overflow: hidden;
  flex-shrink: 0;
  min-height: 2rem;
}

.stage-pipeline-cell__collapsed {
  flex-shrink: 0;
  transition: opacity 0.25s ease;
}
.stage-pipeline-cell--expanded .stage-pipeline-cell__collapsed {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  opacity: 0;
  pointer-events: none;
}

.stage-pipeline-cell__expanded {
  max-width: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-width 0.35s ease-out, opacity 0.25s ease;
}
.stage-pipeline-cell--expanded .stage-pipeline-cell__expanded {
  max-width: 80rem;
  opacity: 1;
}
</style>
