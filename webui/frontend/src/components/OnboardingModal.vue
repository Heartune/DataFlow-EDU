<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const emit = defineEmits<{ (e: 'close'): void }>();

const auth = useAuthStore();
const router = useRouter();

const steps = [
  {
    label: '上传教材',
    sub: 'PDF / PPT',
    d: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12',
  },
  {
    label: '配置题型',
    sub: '学科 & 层级',
    d: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
  },
  {
    label: 'AI 生成',
    sub: '3~15 分钟',
    d: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  },
  {
    label: '导出题库',
    sub: 'Word / PDF',
    d: 'M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  },
];

async function dismiss() {
  await auth.markOnboardingDone();
  emit('close');
}

async function getStarted() {
  await auth.markOnboardingDone();
  emit('close');
  router.push('/teacher/tasks/new');
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg relative overflow-hidden">

        <!-- 关闭按钮 -->
        <button
          class="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          aria-label="关闭"
          @click="dismiss"
        >
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <!-- 顶部深色区域 -->
        <div class="bg-slate-900 px-8 pt-8 pb-6">
          <div class="flex items-center gap-3 mb-3">
            <div class="w-9 h-9 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
              <svg class="w-5 h-5 text-slate-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h1 class="text-lg font-bold text-white">欢迎使用 DataFlow-EDU</h1>
          </div>
          <p class="text-slate-300 text-sm leading-relaxed">
            上传一份教科书、教辅书、课件等教学材料（PDF/PPT/PPTX 格式），<br />
            系统自动生成高质量习题与解析，<br />
            支持一键导出为试卷，<br />
            从繁琐冗杂的出题工作中解放教师生产力。
          </p>
        </div>

        <!-- 流程步骤 -->
        <div class="px-8 py-6">
          <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-5">四步完成题库生成</p>

          <div class="flex items-start gap-1">
            <template v-for="(step, i) in steps" :key="i">
              <div class="flex-1 flex flex-col items-center text-center gap-2">
                <div class="w-11 h-11 rounded-xl bg-slate-100 flex items-center justify-center">
                  <svg class="w-5 h-5 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" :d="step.d" />
                  </svg>
                </div>
                <div>
                  <div class="text-xs font-semibold text-slate-800">{{ step.label }}</div>
                  <div class="text-[11px] text-slate-400 mt-0.5">{{ step.sub }}</div>
                </div>
              </div>
              <div v-if="i < steps.length - 1" class="flex-shrink-0 mt-4">
                <svg class="w-4 h-4 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </template>
          </div>

          <!-- 耗时提示 -->
          <div class="mt-5 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
            <svg class="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p class="text-xs text-amber-700 leading-relaxed">
              全流程通常需要 <strong>3~15 分钟</strong>，<br />
              具体取决于您上传材料的页数和 AI 服务响应速度。<br />
              提交后可离开页面，完成后随时回来查看结果。
            </p>
          </div>
        </div>

        <!-- 底部操作区 -->
        <div class="px-8 pb-6 flex items-center justify-between border-t border-slate-100 pt-4">
          <button
            class="text-sm text-slate-400 hover:text-slate-600 transition-colors"
            @click="dismiss"
          >
            稍后再说
          </button>
          <button
            class="px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors"
            @click="getStarted"
          >
            创建我的第一个任务 →
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>
