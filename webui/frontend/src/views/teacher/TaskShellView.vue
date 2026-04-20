<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api } from '@/api/client';

const props = defineProps<{ id: string }>();
const route = useRoute();

interface TaskBrief {
  id: string;
  name: string;
  status: 'created' | 'running' | 'succeeded' | 'failed' | 'cancelled';
}

const task = ref<TaskBrief | null>(null);
const error = ref('');

async function loadTask() {
  try {
    const { data } = await api.get(`/tasks/${props.id}`);
    task.value = {
      id: data.task.id,
      name: data.task.name,
      status: data.task.status,
    };
  } catch (err: any) {
    error.value = err?.response?.data?.error || err?.message || '加载任务失败';
  }
}

const tabs = computed(() => [
  { name: 'teacher-task-progress', label: '进度', to: { name: 'teacher-task-progress', params: { id: props.id } } },
  { name: 'teacher-task-wizard', label: '配置', to: { name: 'teacher-task-wizard', params: { id: props.id } } },
  { name: 'teacher-task-edit', label: '编辑', to: { name: 'teacher-task-edit', params: { id: props.id } } },
  { name: 'teacher-task-export', label: '导出', to: { name: 'teacher-task-export', params: { id: props.id } } },
]);

const statusLabel: Record<string, string> = {
  created: '待启动',
  running: '运行中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const statusClass: Record<string, string> = {
  created: 'bg-slate-50 text-slate-600 border-slate-200',
  running: 'bg-amber-50 text-amber-700 border-amber-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  cancelled: 'bg-slate-100 text-slate-600 border-slate-300',
};

onMounted(loadTask);
watch(() => route.fullPath, () => {
  // 切 tab 时不重拉，只在路由 id 变化时拉
}, { immediate: false });
watch(() => props.id, loadTask);
</script>

<template>
  <div>
    <router-link to="/teacher/tasks" class="text-sm text-slate-500 hover:text-slate-900">
      ← 返回任务列表
    </router-link>

    <div v-if="error" class="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4 mt-4">
      {{ error }}
    </div>

    <div v-if="task" class="mt-4 mb-4 flex items-center justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <h1 class="text-xl font-bold text-slate-900 truncate">{{ task.name }}</h1>
        <p class="text-xs text-slate-500 mt-1 font-mono break-all">{{ task.id }}</p>
      </div>
      <span
        v-if="task.status"
        :class="['px-3 py-1 rounded-full text-xs border', statusClass[task.status] || 'bg-slate-50 text-slate-600 border-slate-200']"
      >
        {{ statusLabel[task.status] || task.status }}
      </span>
    </div>

    <nav v-if="task" class="border-b border-slate-200 mb-4">
      <ul class="flex gap-1">
        <li v-for="t in tabs" :key="t.name">
          <router-link
            :to="t.to"
            class="inline-block px-4 py-2 text-sm border-b-2 -mb-[2px] transition"
            active-class="border-slate-900 text-slate-900 font-medium"
            exact-active-class="border-slate-900 text-slate-900 font-medium"
            :class="['border-transparent text-slate-500 hover:text-slate-900']"
          >
            {{ t.label }}
          </router-link>
        </li>
      </ul>
    </nav>

    <router-view v-if="task" :id="props.id" :task-status="task.status" :task-name="task.name" />
  </div>
</template>
