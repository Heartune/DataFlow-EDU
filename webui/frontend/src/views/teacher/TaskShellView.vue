<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api } from '@/api/client';

const props = defineProps<{ id: string }>();
const route = useRoute();

interface TaskBrief {
  id: string;
  name: string;
  status: 'created' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
}

const task = ref<TaskBrief | null>(null);
const error = ref('');
const titleEditing = ref(false);
const titleDraft = ref('');
const titleSaving = ref(false);
const titleInput = ref<HTMLInputElement | null>(null);
const titleError = ref('');

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
  { name: 'teacher-task-stats', label: '统计 / 编辑', to: { name: 'teacher-task-stats', params: { id: props.id } } },
  { name: 'teacher-task-wizard', label: '配置', to: { name: 'teacher-task-wizard', params: { id: props.id } } },
  { name: 'teacher-task-export', label: '导出', to: { name: 'teacher-task-export', params: { id: props.id } } },
]);

const statusLabel: Record<string, string> = {
  created: '待启动',
  queued: '排队中',
  running: '运行中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const statusClass: Record<string, string> = {
  created: 'bg-slate-50 text-slate-600 border-slate-200',
  queued: 'bg-sky-50 text-sky-700 border-sky-200',
  running: 'bg-amber-50 text-amber-700 border-amber-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  cancelled: 'bg-slate-100 text-slate-600 border-slate-300',
};

function startTitleEdit() {
  if (!task.value) return;
  titleEditing.value = true;
  titleDraft.value = task.value.name;
  titleError.value = '';
  nextTick(() => titleInput.value?.focus());
}

function cancelTitleEdit() {
  titleEditing.value = false;
  titleDraft.value = '';
  titleError.value = '';
}

async function saveTitleEdit() {
  if (!task.value || titleSaving.value) return;
  const next = titleDraft.value.trim();
  if (!next) {
    titleError.value = '名称不能为空';
    return;
  }
  if (next === task.value.name) {
    cancelTitleEdit();
    return;
  }
  titleSaving.value = true;
  titleError.value = '';
  try {
    const { data } = await api.patch(`/tasks/${props.id}`, { name: next });
    task.value.name = data.name;
    cancelTitleEdit();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    titleError.value =
      code === 'name_too_long' ? '名称过长（最多 200 字）' : err?.message || '重命名失败';
  } finally {
    titleSaving.value = false;
  }
}

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
      <div class="min-w-0 flex-1">
        <template v-if="titleEditing">
          <div class="flex flex-col gap-2 max-w-xl">
            <div class="flex flex-wrap items-center gap-2">
              <input
                ref="titleInput"
                v-model="titleDraft"
                type="text"
                maxlength="200"
                class="flex-1 min-w-[12rem] px-3 py-2 border border-slate-300 rounded-lg text-xl font-bold text-slate-900"
                :disabled="titleSaving"
                @keydown.enter.prevent="saveTitleEdit"
                @keydown.esc.prevent="cancelTitleEdit"
              />
              <button
                type="button"
                class="px-3 py-2 text-sm rounded-lg bg-slate-900 text-white disabled:opacity-50"
                :disabled="titleSaving"
                @click="saveTitleEdit"
              >
                {{ titleSaving ? '保存中…' : '保存' }}
              </button>
              <button
                type="button"
                class="px-3 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
                :disabled="titleSaving"
                @click="cancelTitleEdit"
              >
                取消
              </button>
            </div>
            <p v-if="titleError" class="text-sm text-rose-600">{{ titleError }}</p>
          </div>
        </template>
        <template v-else>
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-xl font-bold text-slate-900 truncate">{{ task.name }}</h1>
            <button
              type="button"
              class="shrink-0 px-3 py-1.5 text-sm border border-slate-300 rounded-lg text-slate-700 hover:border-slate-900 disabled:opacity-50"
              @click="startTitleEdit"
            >
              重命名
            </button>
          </div>
        </template>
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
