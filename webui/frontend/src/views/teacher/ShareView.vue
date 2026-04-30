<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

const props = defineProps<{ token: string }>();

interface ShareItem {
  question?: string;
  answer?: string;
  type?: string;
  options?: string[];
  explanation?: string;
  category?: string;
  subcategory?: string;
  difficulty?: string | number;
  ability_level?: string;
}

interface ShareData {
  task_name: string;
  stage: string | null;
  item_count: number;
  items: ShareItem[];
  generated_at: number;
  expires_at: number | null;
}

const loading = ref(true);
const errorMsg = ref('');
const data = ref<ShareData | null>(null);

const PAGE_SIZE = 20;
const page = ref(1);

const pageItems = computed(() => {
  if (!data.value) return [];
  const start = (page.value - 1) * PAGE_SIZE;
  return data.value.items.slice(start, start + PAGE_SIZE);
});

const totalPages = computed(() =>
  data.value ? Math.ceil(data.value.items.length / PAGE_SIZE) : 0
);

async function load() {
  loading.value = true;
  errorMsg.value = '';
  try {
    const resp = await fetch(`/api/share/${encodeURIComponent(props.token)}`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      if (resp.status === 404) errorMsg.value = '分享链接不存在或已被删除';
      else if (resp.status === 410)
        errorMsg.value = body.error === 'share_expired' ? '该分享链接已过期' : '分享链接不可用';
      else errorMsg.value = body.error || `请求失败 (${resp.status})`;
      return;
    }
    data.value = await resp.json();
  } catch {
    errorMsg.value = '加载失败，请检查网络连接';
  } finally {
    loading.value = false;
  }
}

function fmtDate(ts: number) {
  return new Date(ts).toLocaleString();
}

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i);
}

onMounted(load);
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- 顶栏 -->
    <div class="bg-white border-b border-slate-200 px-4 py-3">
      <div class="max-w-4xl mx-auto flex items-center gap-3">
        <span class="text-slate-900 font-semibold text-sm">DataFlow-EDU</span>
        <span class="text-slate-300">·</span>
        <span class="text-xs text-slate-500 bg-sky-50 border border-sky-200 text-sky-700 px-2 py-0.5 rounded-full">
          只读预览
        </span>
      </div>
    </div>

    <div class="max-w-4xl mx-auto px-4 py-8">
      <!-- 加载中 -->
      <div v-if="loading" class="text-center py-20 text-slate-500">加载中...</div>

      <!-- 错误 -->
      <div
        v-else-if="errorMsg"
        class="bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl p-8 text-center"
      >
        <p class="text-base font-medium">{{ errorMsg }}</p>
        <p class="text-sm mt-2 text-rose-500">请联系分享者确认链接是否有效</p>
      </div>

      <!-- 内容 -->
      <div v-else-if="data">
        <div class="mb-6">
          <h1 class="text-2xl font-bold text-slate-900">{{ data.task_name }}</h1>
          <div class="flex items-center gap-4 mt-2 text-sm text-slate-500 flex-wrap">
            <span>共 {{ data.item_count }} 题</span>
            <span v-if="data.stage">来源阶段：{{ data.stage }}</span>
            <span>生成时间：{{ fmtDate(data.generated_at) }}</span>
            <span v-if="data.expires_at" class="text-amber-600">
              链接有效至 {{ fmtDate(data.expires_at) }}
            </span>
            <span v-else class="text-slate-400">链接永久有效</span>
          </div>
          <p class="mt-3 text-xs text-slate-400 bg-slate-100 rounded-xl px-3 py-2 inline-block">
            本页面为只读预览，内容由 DataFlow-EDU 自动生成，仅供参考
          </p>
        </div>

        <!-- 题目列表 -->
        <div v-if="data.items.length === 0" class="text-slate-500 py-12 text-center">
          暂无题目数据
        </div>
        <div v-else class="space-y-4">
          <div
            v-for="(item, idx) in pageItems"
            :key="idx"
            class="bg-white border border-slate-200 rounded-2xl p-5"
          >
            <div class="flex items-start gap-3">
              <span class="text-xs text-slate-400 bg-slate-100 rounded-lg px-2 py-0.5 whitespace-nowrap mt-0.5">
                {{ (page - 1) * 20 + idx + 1 }}
              </span>
              <div class="flex-1 min-w-0">
                <!-- 题目信息行 -->
                <div class="flex items-center gap-2 mb-2 flex-wrap">
                  <span
                    v-if="item.type"
                    class="text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded-full"
                  >
                    {{ item.type }}
                  </span>
                  <span
                    v-if="item.difficulty"
                    class="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full"
                  >
                    难度 {{ item.difficulty }}
                  </span>
                  <span v-if="item.category" class="text-xs text-slate-400">
                    {{ item.category }}{{ item.subcategory ? ' › ' + item.subcategory : '' }}
                  </span>
                </div>

                <!-- 题干 -->
                <p class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
                  {{ item.question || '（题干缺失）' }}
                </p>

                <!-- 选项 -->
                <div v-if="item.options && item.options.length" class="mt-2 space-y-1">
                  <div
                    v-for="(opt, oi) in item.options"
                    :key="oi"
                    class="text-sm text-slate-700 flex items-start gap-2"
                  >
                    <span class="font-medium text-slate-500 w-4 flex-shrink-0">{{ optionLabel(oi) }}.</span>
                    <span>{{ opt }}</span>
                  </div>
                </div>

                <!-- 答案 + 解析 -->
                <div class="mt-3 pt-3 border-t border-slate-100 space-y-1">
                  <p v-if="item.answer" class="text-sm">
                    <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded mr-1">答案</span>
                    <span class="text-slate-800">{{ item.answer }}</span>
                  </p>
                  <p v-if="item.explanation" class="text-sm text-slate-600 leading-relaxed">
                    <span class="text-xs font-medium text-slate-500">解析：</span>{{ item.explanation }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="mt-8 flex items-center justify-center gap-2">
          <button
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            :disabled="page === 1"
            @click="page--"
          >
            上一页
          </button>
          <span class="text-sm text-slate-500">
            {{ page }} / {{ totalPages }}（共 {{ data.item_count }} 题）
          </span>
          <button
            class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            :disabled="page === totalPages"
            @click="page++"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
