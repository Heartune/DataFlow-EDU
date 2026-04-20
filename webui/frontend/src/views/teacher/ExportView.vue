<script setup lang="ts">
import { ref } from 'vue';
import { TOKEN_KEY } from '@/api/client';

const props = defineProps<{ id: string; taskName?: string }>();

const stage = ref<'3_8_mcq_verified' | '3_7_translated' | '3_4_domain_refined'>('3_8_mcq_verified');
const downloading = ref(false);
const error = ref('');
const info = ref('');

const STAGE_OPTIONS = [
  { value: '3_8_mcq_verified', label: '3.8 MCQ Verify (推荐：选择题已校验)' },
  { value: '3_7_translated', label: '3.7 Translated（已加多语言译文）' },
  { value: '3_4_domain_refined', label: '3.4 Domain Refined（学科精炼后）' },
] as const;

async function downloadJson() {
  downloading.value = true;
  error.value = '';
  info.value = '';
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const url = `/api/tasks/${props.id}/export?format=json&stage=${encodeURIComponent(stage.value)}`;
    const resp = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!resp.ok) {
      let msg = `下载失败 (${resp.status})`;
      try {
        const data = await resp.json();
        msg = data.message || data.error || msg;
        if (data.error === 'stage_not_ready' || data.error === 'empty_stage') {
          msg = '该阶段尚未产出任何文件，无法导出';
        }
      } catch {
        // ignore
      }
      error.value = msg;
      return;
    }
    const blob = await resp.blob();
    const cd = resp.headers.get('Content-Disposition') || '';
    let filename = `${props.taskName || 'task'}_${stage.value}.zip`;
    const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
    if (m) {
      try {
        filename = decodeURIComponent(m[1]);
      } catch {
        // ignore
      }
    }
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objectUrl);
    info.value = `已下载 ${filename}`;
  } catch (err: any) {
    error.value = err?.message || '下载失败';
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <div>
    <p v-if="error" class="text-sm text-rose-600 mb-3">{{ error }}</p>
    <p v-if="info" class="text-sm text-emerald-600 mb-3">{{ info }}</p>

    <div class="bg-white border border-slate-200 rounded-2xl p-5 mb-4">
      <label class="text-sm text-slate-600 flex items-center gap-2 flex-wrap">
        导出阶段
        <select v-model="stage" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option v-for="o in STAGE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <p class="text-xs text-slate-400 mt-2">选择哪个阶段的产物作为本次导出依据。3.8 是最干净的成品。</p>
    </div>

    <div class="grid sm:grid-cols-3 gap-4">
      <!-- JSON -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col">
        <div class="text-3xl mb-3">📦</div>
        <h3 class="text-base font-semibold text-slate-900">JSON 数据包</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          将所选阶段下所有 <code>*.json</code> 打成 zip 下载。完整字段，便于后续接入大模型微调或自定义脚本处理。
        </p>
        <button
          class="mt-4 w-full px-3 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
          :disabled="downloading"
          @click="downloadJson"
        >
          {{ downloading ? '打包中...' : '下载 JSON 包' }}
        </button>
      </div>

      <!-- Word -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col relative opacity-60">
        <span class="absolute top-3 right-3 text-[10px] px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">M3 推出</span>
        <div class="text-3xl mb-3">📄</div>
        <h3 class="text-base font-semibold text-slate-900">Word 试卷</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          按题型分组、自动排版，适合直接打印发卷使用，附带答案与解析单独成册。
        </p>
        <button class="mt-4 w-full px-3 py-2 bg-slate-200 text-slate-500 rounded-lg text-sm cursor-not-allowed" disabled>
          敬请期待
        </button>
      </div>

      <!-- PDF -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col relative opacity-60">
        <span class="absolute top-3 right-3 text-[10px] px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full">M3 推出</span>
        <div class="text-3xl mb-3">📕</div>
        <h3 class="text-base font-semibold text-slate-900">PDF 试卷</h3>
        <p class="text-xs text-slate-500 mt-1 leading-relaxed flex-1">
          与 Word 排版一致，导出为可直接分发的 PDF。支持多语言（含法语翻译版本）。
        </p>
        <button class="mt-4 w-full px-3 py-2 bg-slate-200 text-slate-500 rounded-lg text-sm cursor-not-allowed" disabled>
          敬请期待
        </button>
      </div>
    </div>
  </div>
</template>
