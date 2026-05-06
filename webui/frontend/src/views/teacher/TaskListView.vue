<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { api } from '@/api/client';
import { parseTaskError } from '@/utils/errorMessages';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Task {
  id: string;
  name: string;
  status: 'created' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  current_stage: string | null;
  created_at: number;
  updated_at: number;
  meta?: { error?: string; [key: string]: unknown };
  folders: Array<{ id: string; name: string }>;
}

interface FolderNode {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  created_at: number;
  task_count: number;
  children: FolderNode[];
}

interface FlatFolder extends Omit<FolderNode, 'children'> {
  depth: number;
  hasChildren: boolean;
  children: FolderNode[];
}

// ── 任务状态 ─────────────────────────────────────────────────────────────────

const tasks = ref<Task[]>([]);
const loadingTasks = ref(false);
const errorTasks = ref('');
const actionMsg = ref('');
const actionBusy = ref<Record<string, boolean>>({});
const statusFilter = ref<string>('all');
const selected = ref<Set<string>>(new Set());
const bulkDeleting = ref(false);
const confirmDeleteTask = ref<Task | null>(null);
const singleDeleting = ref(false);

const filterOptions = [
  { value: 'all', label: '全部' },
  { value: 'created', label: '待启动' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '运行中' },
  { value: 'succeeded', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
];

const statusLabel: Record<Task['status'], string> = {
  created: '待启动', queued: '排队中', running: '运行中',
  succeeded: '已完成', failed: '失败', cancelled: '已取消',
};
const statusClass: Record<Task['status'], string> = {
  created: 'bg-slate-100 text-slate-600',
  queued: 'bg-sky-100 text-sky-700',
  running: 'bg-amber-100 text-amber-700',
  succeeded: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-slate-200 text-slate-600',
};
const errorLabel: Record<string, string> = {
  no_progress_to_resume: '没有可恢复的历史进度，请在任务详情页改用「从头重新生成」',
  nothing_to_resume: '所有阶段都已完成，无需继续',
  user_has_running_task: '你已有任务正在生成，等它结束后再启动新任务',
  task_already_running: '任务已在运行中',
  missing_llm_key: 'LLM Key 未配置，请联系管理员',
  pdf_missing: '原始 PDF 已丢失，无法继续',
};

// ── 文件夹状态 ────────────────────────────────────────────────────────────────

const folders = ref<FolderNode[]>([]);
const loadingFolders = ref(false);
const activeFolderId = ref<string>('all'); // 'all' | 'uncategorized' | <uuid>
const expandedFolders = ref<Set<string>>(new Set());

// 内联编辑
const editingFolderId = ref<string | null>(null); // null=新建, 其他=重命名
const editingParentId = ref<string | null>(null);  // 新建时的父文件夹
const editingName = ref('');
const editingInput = ref<HTMLInputElement | null>(null);
const editingError = ref('');

// 菜单
const openMenuFolderId = ref<string | null>(null);

// 拖放（任务→文件夹）
const dragOverFolderId = ref<string | null>(null);

// 文件夹拖动排序
const draggingFolderId = ref<string | null>(null);
const dropBeforeFolderId = ref<string | null>(null); // 插入到此节点之前

// ── 扁平化树 ──────────────────────────────────────────────────────────────────

function flattenTree(nodes: FolderNode[], depth = 0): FlatFolder[] {
  const result: FlatFolder[] = [];
  for (const n of nodes) {
    result.push({ ...n, depth, hasChildren: n.children.length > 0 });
    if (expandedFolders.value.has(n.id)) {
      result.push(...flattenTree(n.children, depth + 1));
    }
  }
  return result;
}

const flatFolders = computed(() => flattenTree(folders.value));

// ── 加载数据 ──────────────────────────────────────────────────────────────────

async function loadFolders() {
  loadingFolders.value = true;
  try {
    const { data } = await api.get('/folders');
    folders.value = data.folders;
  } catch {
    // 静默失败，文件夹加载错误不阻塞任务列表
  } finally {
    loadingFolders.value = false;
  }
}

async function loadTasks() {
  loadingTasks.value = true;
  errorTasks.value = '';
  selected.value = new Set();
  try {
    const params: Record<string, string> = {};
    if (activeFolderId.value !== 'all') {
      params.folder_id = activeFolderId.value;
    }
    const { data } = await api.get('/tasks', { params });
    tasks.value = data.tasks;
  } catch (err: any) {
    errorTasks.value = err?.message || '加载失败';
  } finally {
    loadingTasks.value = false;
  }
}

async function load() {
  await Promise.all([loadFolders(), loadTasks()]);
}

onMounted(load);

// ── 筛选 / 选择 ───────────────────────────────────────────────────────────────

const filteredTasks = computed(() => {
  if (statusFilter.value === 'all') return tasks.value;
  return tasks.value.filter((t) => t.status === statusFilter.value);
});

function canSelect(t: Task) {
  return t.status !== 'running' && t.status !== 'queued';
}

const allSelectableFiltered = computed(() =>
  filteredTasks.value.filter(canSelect).map((t) => t.id)
);
const allChecked = computed(
  () =>
    allSelectableFiltered.value.length > 0 &&
    allSelectableFiltered.value.every((id) => selected.value.has(id))
);
const indeterminate = computed(
  () => !allChecked.value && allSelectableFiltered.value.some((id) => selected.value.has(id))
);

function toggleAll() {
  if (allChecked.value) {
    allSelectableFiltered.value.forEach((id) => selected.value.delete(id));
  } else {
    allSelectableFiltered.value.forEach((id) => selected.value.add(id));
  }
  selected.value = new Set(selected.value);
}

function toggleOne(id: string) {
  selected.value.has(id) ? selected.value.delete(id) : selected.value.add(id);
  selected.value = new Set(selected.value);
}

function onFilterChange() {
  const visible = new Set(filteredTasks.value.map((t) => t.id));
  selected.value = new Set([...selected.value].filter((id) => visible.has(id)));
}

// ── 任务操作 ──────────────────────────────────────────────────────────────────

/** yyyy/mm/dd 上午/下午 hh:mm（12 小时制，与界面中文习惯一致） */
function fmtDate(ts: number) {
  const d = new Date(ts);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h24 = d.getHours();
  const period = h24 < 12 ? '上午' : '下午';
  let h12 = h24 % 12;
  if (h12 === 0) h12 = 12;
  const hh = String(h12).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${y}/${mo}/${day} ${period} ${hh}:${mm}`;
}

async function resumeTask(t: Task) {
  if (actionBusy.value[t.id]) return;
  actionBusy.value = { ...actionBusy.value, [t.id]: true };
  actionMsg.value = '';
  try {
    await api.post(`/tasks/${t.id}/resume`);
    await loadTasks();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    actionMsg.value = errorLabel[code] || err?.response?.data?.message || err?.message || '续跑失败';
  } finally {
    actionBusy.value = { ...actionBusy.value, [t.id]: false };
  }
}

function canResume(t: Task) {
  return t.status === 'failed' || t.status === 'cancelled' || t.status === 'succeeded';
}

function deleteTask(task: Task) {
  confirmDeleteTask.value = task;
}

async function confirmDeleteOne() {
  const task = confirmDeleteTask.value;
  if (!task || singleDeleting.value) return;
  singleDeleting.value = true;
  try {
    await api.delete(`/tasks/${task.id}`);
    confirmDeleteTask.value = null;
    await loadTasks();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (err?.response?.status === 409) {
      actionMsg.value = code === 'task_is_queued'
        ? '任务排队中，请等待或取消后再删除'
        : '任务正在运行，请先停止后再删除';
    } else {
      actionMsg.value = '删除失败，请重试';
    }
    confirmDeleteTask.value = null;
  } finally {
    singleDeleting.value = false;
  }
}

async function bulkDelete() {
  if (selected.value.size === 0 || bulkDeleting.value) return;
  const ids = [...selected.value];
  if (!confirm(`确认删除选中的 ${ids.length} 个任务？此操作不可撤销。`)) return;
  bulkDeleting.value = true;
  actionMsg.value = '';
  const results = await Promise.allSettled(ids.map((id) => api.delete(`/tasks/${id}`)));
  const failed = results.filter((r) => r.status === 'rejected').length;
  bulkDeleting.value = false;
  if (failed > 0) {
    actionMsg.value = `${ids.length - failed} 个删除成功，${failed} 个失败（可能仍在运行）`;
  }
  await loadTasks();
}

// ── 文件夹导航 ────────────────────────────────────────────────────────────────

function selectFolder(id: string) {
  activeFolderId.value = id;
  openMenuFolderId.value = null;
  loadTasks();
}

function toggleExpand(id: string) {
  if (expandedFolders.value.has(id)) {
    expandedFolders.value.delete(id);
  } else {
    expandedFolders.value.add(id);
  }
  expandedFolders.value = new Set(expandedFolders.value);
}

// ── 文件夹 CRUD ───────────────────────────────────────────────────────────────

function startNewRootFolder() {
  editingFolderId.value = '__new__';
  editingParentId.value = null;
  editingName.value = '';
  editingError.value = '';
  openMenuFolderId.value = null;
  nextTick(() => editingInput.value?.focus());
}

function startNewSubFolder(parentId: string) {
  expandedFolders.value.add(parentId);
  expandedFolders.value = new Set(expandedFolders.value);
  editingFolderId.value = '__new__';
  editingParentId.value = parentId;
  editingName.value = '';
  editingError.value = '';
  openMenuFolderId.value = null;
  nextTick(() => editingInput.value?.focus());
}

function startRename(folder: FlatFolder) {
  editingFolderId.value = folder.id;
  editingParentId.value = folder.parent_id;
  editingName.value = folder.name;
  editingError.value = '';
  openMenuFolderId.value = null;
  nextTick(() => editingInput.value?.focus());
}

function cancelEdit() {
  editingFolderId.value = null;
  editingParentId.value = null;
  editingName.value = '';
  editingError.value = '';
}

async function commitEdit() {
  const name = editingName.value.trim();
  if (!name) { cancelEdit(); return; }
  editingError.value = '';
  try {
    if (editingFolderId.value === '__new__') {
      await api.post('/folders', { name, parent_id: editingParentId.value ?? undefined });
    } else {
      await api.patch(`/folders/${editingFolderId.value}`, { name });
    }
    cancelEdit();
    await loadFolders();
  } catch (err: any) {
    const code = err?.response?.data?.error;
    editingError.value = code === 'duplicate_name' ? '同级文件夹下已存在该名称' : '保存失败';
  }
}

function onEditKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') commitEdit();
  else if (e.key === 'Escape') cancelEdit();
}

async function deleteFolder(folder: FlatFolder) {
  const hasChildren = folder.hasChildren;
  const msg = hasChildren
    ? `确认删除文件夹「${folder.name}」及其所有子文件夹？其中的任务不会被删除，只会解除归类。`
    : `确认删除文件夹「${folder.name}」？其中的任务不会被删除，只会解除归类。`;
  if (!confirm(msg)) return;
  try {
    await api.delete(`/folders/${folder.id}`);
    if (activeFolderId.value === folder.id) {
      activeFolderId.value = 'all';
    }
    await Promise.all([loadFolders(), loadTasks()]);
  } catch {
    alert('删除失败，请重试');
  }
  openMenuFolderId.value = null;
}

// ── 任务拖到文件夹 ────────────────────────────────────────────────────────────

function onTaskDragStart(e: DragEvent, taskId: string) {
  if (!e.dataTransfer) return;
  e.dataTransfer.setData('type', 'task');
  e.dataTransfer.setData('task_id', taskId);
  e.dataTransfer.effectAllowed = 'link';
}

function onFolderDragEnter(e: DragEvent, folderId: string) {
  e.preventDefault();
  if (!e.dataTransfer) return;
  // 仅在任务拖拽时高亮（文件夹自身拖拽时不高亮目标文件夹）
  if (!draggingFolderId.value) {
    dragOverFolderId.value = folderId;
  }
}

function onFolderDragLeave(_e: DragEvent, folderId: string) {
  if (dragOverFolderId.value === folderId) dragOverFolderId.value = null;
}

async function onFolderDrop(e: DragEvent, folderId: string) {
  e.preventDefault();
  dragOverFolderId.value = null;
  if (!e.dataTransfer) return;
  const type = e.dataTransfer.getData('type');
  const taskId = e.dataTransfer.getData('task_id');
  if (type === 'task' && taskId) {
    try {
      await api.post(`/folders/${folderId}/tasks/${taskId}`);
      await Promise.all([loadFolders(), loadTasks()]);
    } catch {
      // 静默失败
    }
  }
}

// ── 文件夹拖动排序 ────────────────────────────────────────────────────────────

function onFolderHandleDragStart(e: DragEvent, folderId: string) {
  if (!e.dataTransfer) return;
  draggingFolderId.value = folderId;
  e.dataTransfer.setData('type', 'folder');
  e.dataTransfer.setData('folder_id', folderId);
  e.dataTransfer.effectAllowed = 'move';
}

function onFolderRowDragOver(e: DragEvent, folderId: string) {
  e.preventDefault();
  if (!e.dataTransfer) return;
  const type = e.dataTransfer.getData('type') || '';
  if (type === 'folder' || draggingFolderId.value) {
    dropBeforeFolderId.value = folderId;
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }
}

function onFolderRowDragLeave(_e: DragEvent) {
  dropBeforeFolderId.value = null;
}

async function onFolderRowDrop(e: DragEvent, targetFolderId: string) {
  e.preventDefault();
  dropBeforeFolderId.value = null;
  const movingId = draggingFolderId.value;
  draggingFolderId.value = null;
  if (!movingId || movingId === targetFolderId) return;

  // 找到被移动文件夹和目标文件夹，计算新 sort_order（同级移动）
  const movingFlat = flatFolders.value.find((f) => f.id === movingId);
  const targetFlat = flatFolders.value.find((f) => f.id === targetFolderId);
  if (!movingFlat || !targetFlat || movingFlat.parent_id !== targetFlat.parent_id) {
    return; // 只支持同级排序
  }

  // 同级文件夹排序列表
  const siblings = flatFolders.value.filter((f) => f.parent_id === movingFlat.parent_id);
  const targetIdx = siblings.findIndex((f) => f.id === targetFolderId);
  let newOrder: number;
  if (targetIdx === 0) {
    newOrder = siblings[0].sort_order - 1000;
  } else {
    const prev = siblings[targetIdx - 1];
    newOrder = Math.floor((prev.sort_order + siblings[targetIdx].sort_order) / 2);
  }

  try {
    await api.patch(`/folders/${movingId}`, { sort_order: newOrder });
    await loadFolders();
  } catch {
    // 静默失败
  }
}

function onDragEnd() {
  draggingFolderId.value = null;
  dropBeforeFolderId.value = null;
  dragOverFolderId.value = null;
}

// ── 菜单管理 ──────────────────────────────────────────────────────────────────

function toggleMenu(folderId: string, e: Event) {
  e.stopPropagation();
  openMenuFolderId.value = openMenuFolderId.value === folderId ? null : folderId;
}

function closeMenu() {
  openMenuFolderId.value = null;
}

// ── 计算当前视图标题 ──────────────────────────────────────────────────────────

const activeViewLabel = computed(() => {
  if (activeFolderId.value === 'all') return '全部任务';
  if (activeFolderId.value === 'uncategorized') return '未分类';
  const flat = flatFolders.value.find((f) => f.id === activeFolderId.value);
  return flat ? flat.name : '我的任务';
});
</script>

<template>
  <div class="flex flex-col lg:flex-row gap-4 lg:gap-6 h-full min-w-0" @click="closeMenu">

    <!-- ── 左侧文件夹侧边栏 ──────────────────────────────────────────────── -->
    <aside class="w-full lg:w-48 flex-shrink-0 flex flex-col">
      <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-1">文件夹</div>

      <!-- 全部任务 -->
      <button
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm w-full text-left mb-0.5 transition-colors"
        :class="activeFolderId === 'all' ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'"
        @click="selectFolder('all')"
      >
        <svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
        </svg>
        <span class="truncate flex-1">全部任务</span>
      </button>

      <!-- 未分类 -->
      <button
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm w-full text-left mb-1 transition-colors"
        :class="activeFolderId === 'uncategorized' ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'"
        @click="selectFolder('uncategorized')"
      >
        <svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <span class="truncate flex-1">未分类</span>
      </button>

      <div class="border-t border-slate-100 mb-1"></div>

      <!-- 文件夹树（扁平化渲染） -->
      <div class="flex-1 overflow-y-auto min-h-0 max-h-64 lg:max-h-none px-1">
        <div v-if="loadingFolders" class="text-xs text-slate-400 px-3 py-2">加载中...</div>

        <template v-for="folder in flatFolders" :key="folder.id">
          <!-- 拖放排序指示线 -->
          <div
            v-if="dropBeforeFolderId === folder.id && draggingFolderId && draggingFolderId !== folder.id"
            class="h-0.5 bg-blue-400 rounded mx-0.5"
          ></div>

          <!-- 文件夹行 -->
          <div
            class="group relative flex items-center rounded-lg text-sm mb-0.5 cursor-pointer select-none transition-colors"
            :style="{ paddingLeft: `${folder.depth * 12 + 4}px` }"
            :class="[
              activeFolderId === folder.id ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100',
              dragOverFolderId === folder.id ? 'bg-blue-50 ring-1 ring-inset ring-blue-300' : '',
              draggingFolderId === folder.id ? 'opacity-40' : '',
            ]"
            draggable="true"
            @dragstart.stop="onFolderHandleDragStart($event, folder.id)"
            @dragover.stop="onFolderRowDragOver($event, folder.id)"
            @dragleave.stop="onFolderRowDragLeave($event)"
            @drop.stop="onFolderRowDrop($event, folder.id)"
            @dragend="onDragEnd"
            @dragenter="onFolderDragEnter($event, folder.id)"
            @dragleave.self="onFolderDragLeave($event, folder.id)"
            @drop.prevent="onFolderDrop($event, folder.id)"
            @click="selectFolder(folder.id)"
          >
            <!-- 展开/收起 -->
            <button
              v-if="folder.hasChildren"
              class="w-5 h-5 flex items-center justify-center flex-shrink-0 rounded hover:bg-black/10 mr-0.5"
              @click.stop="toggleExpand(folder.id)"
            >
              <svg class="w-3 h-3 transition-transform" :class="expandedFolders.has(folder.id) ? 'rotate-90' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <span v-else class="w-5 flex-shrink-0"></span>

            <!-- 文件夹图标 -->
            <svg class="w-4 h-4 flex-shrink-0 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
            </svg>

            <!-- 重命名时的输入框 -->
            <template v-if="editingFolderId === folder.id">
              <input
                ref="editingInput"
                v-model="editingName"
                class="flex-1 min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm text-slate-900 outline-none"
                maxlength="64"
                @keydown="onEditKeydown"
                @click.stop
                @blur="commitEdit"
              />
              <span v-if="editingError" class="absolute left-0 top-full mt-0.5 text-xs text-rose-500 bg-white rounded shadow px-2 py-1 z-10 whitespace-nowrap">{{ editingError }}</span>
            </template>
            <template v-else>
              <span class="truncate flex-1 pr-1 py-1.5" @dblclick.stop="startRename(folder)">{{ folder.name }}</span>
              <span
                v-if="folder.task_count > 0"
                class="text-xs px-1 rounded-full flex-shrink-0"
                :class="activeFolderId === folder.id ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'"
              >{{ folder.task_count }}</span>
            </template>

            <!-- "..." 菜单按钮 -->
            <button
              v-if="editingFolderId !== folder.id"
              class="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 ml-0.5 hover:bg-black/10"
              :class="activeFolderId === folder.id ? 'text-white' : 'text-slate-500'"
              @click.stop="toggleMenu(folder.id, $event)"
            >
              <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
              </svg>
            </button>

            <!-- 下拉菜单 -->
            <div
              v-if="openMenuFolderId === folder.id"
              class="absolute right-0 top-6 z-20 bg-white border border-slate-200 rounded-lg shadow-lg py-1 min-w-[120px]"
              @click.stop
            >
              <button class="w-full text-left px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50" @click="startRename(folder)">重命名</button>
              <button class="w-full text-left px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50" @click="startNewSubFolder(folder.id)">新建子文件夹</button>
              <div class="border-t border-slate-100 my-1"></div>
              <button class="w-full text-left px-3 py-1.5 text-sm text-rose-600 hover:bg-rose-50" @click="deleteFolder(folder)">删除</button>
            </div>
          </div>
        </template>

        <!-- 新建根文件夹的内联输入 -->
        <div
          v-if="editingFolderId === '__new__' && editingParentId === null"
          class="flex items-center gap-1 px-3 py-1 mb-0.5"
        >
          <svg class="w-4 h-4 flex-shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
          </svg>
          <input
            ref="editingInput"
            v-model="editingName"
            class="flex-1 min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm text-slate-900 outline-none"
            placeholder="文件夹名称"
            maxlength="64"
            @keydown="onEditKeydown"
            @blur="commitEdit"
          />
        </div>

        <!-- 新建子文件夹的内联输入（显示在对应父文件夹展开后） -->
        <div
          v-if="editingFolderId === '__new__' && editingParentId !== null"
          class="flex items-center gap-1 mb-0.5"
          :style="{ paddingLeft: `${(flatFolders.find(f => f.id === editingParentId)?.depth ?? 0) * 12 + 16 + 4}px` }"
        >
          <svg class="w-4 h-4 flex-shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
          </svg>
          <input
            ref="editingInput"
            v-model="editingName"
            class="flex-1 min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm text-slate-900 outline-none"
            placeholder="子文件夹名称"
            maxlength="64"
            @keydown="onEditKeydown"
            @blur="commitEdit"
          />
        </div>

        <div v-if="editingError && editingFolderId !== '__new__'" class="text-xs text-rose-500 px-3 pb-1">{{ editingError }}</div>
      </div>

      <!-- 新建文件夹按钮 -->
      <button
        class="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-lg w-full"
        @click="startNewRootFolder"
      >
        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        新建文件夹
      </button>
    </aside>

    <!-- ── 右侧任务表 ──────────────────────────────────────────────────────── -->
    <div class="flex-1 min-w-0 flex flex-col">

      <!-- 头部 -->
      <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-5 sm:mb-6 gap-3">
        <div class="min-w-0">
          <h1 class="text-xl sm:text-2xl font-bold text-slate-900 truncate">{{ activeViewLabel }}</h1>
          <p class="text-sm text-slate-500 mt-1">
            {{ activeFolderId === 'all' ? '上传一份教学材料，自动生成高质量习题与解析' : '将任务行拖入左侧文件夹可完成归类。' }}
          </p>
        </div>
        <div class="flex items-center gap-2 w-full sm:w-auto">
          <button
            class="flex-1 sm:flex-initial px-3 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:border-slate-900"
            @click="load"
          >
            刷新
          </button>
          <router-link
            to="/teacher/tasks/new"
            class="flex-1 sm:flex-initial px-3 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-center"
          >
            + 新建任务
          </router-link>
        </div>
      </div>

      <!-- 筛选栏 + 批量操作 -->
      <div class="flex items-center gap-3 mb-4 flex-wrap">
        <div class="flex items-center gap-2">
          <label class="text-sm text-slate-500">筛选：</label>
          <select
            v-model="statusFilter"
            class="text-sm border border-slate-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:border-slate-900"
            @change="onFilterChange"
          >
            <option v-for="opt in filterOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>

        <button
          v-if="selected.size > 0"
          class="px-3 py-1.5 text-sm bg-rose-600 text-white rounded-lg hover:bg-rose-700 disabled:opacity-50"
          :disabled="bulkDeleting"
          @click="bulkDelete"
        >
          {{ bulkDeleting ? '删除中...' : `删除所选 (${selected.size})` }}
        </button>
      </div>

      <p v-if="actionMsg" class="text-sm text-rose-600 mb-3">{{ actionMsg }}</p>

      <!-- 任务列表 -->
      <div v-if="loadingTasks" class="text-slate-500 py-12 text-center">加载中...</div>
      <div v-else-if="errorTasks" class="text-rose-600 py-12 text-center">{{ errorTasks }}</div>
      <div v-else-if="!filteredTasks.length" class="bg-white rounded-2xl border border-slate-200 p-12 text-center">
        <p class="text-slate-500 mb-4">
          {{ statusFilter === 'all' ? '这里还没有任务。' : '当前筛选条件下没有任务。' }}
        </p>
        <router-link
          v-if="statusFilter === 'all' && activeFolderId === 'all'"
          to="/teacher/tasks/new"
          class="inline-block px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800"
        >
          创建第一个任务
        </router-link>
      </div>

      <div v-else class="bg-white rounded-2xl border border-slate-200 overflow-hidden overflow-x-auto">
        <table class="w-full min-w-[56rem] text-sm">
          <thead class="bg-slate-50 text-slate-500">
            <tr>
              <th class="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  :checked="allChecked"
                  :indeterminate="indeterminate"
                  class="rounded"
                  :disabled="allSelectableFiltered.length === 0"
                  @change="toggleAll"
                />
              </th>
              <th class="text-left px-4 py-3 font-medium">名称</th>
              <th class="text-left px-4 py-3 font-medium">状态</th>
              <th class="text-left px-4 py-3 font-medium">当前阶段</th>
              <th class="text-left px-4 py-3 font-medium">创建时间</th>
              <th class="text-left px-4 py-3 font-medium">更新时间</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr
              v-for="t in filteredTasks"
              :key="t.id"
              class="hover:bg-slate-50 transition-colors"
              :class="{ 'bg-slate-50/60': selected.has(t.id) }"
              draggable="true"
              @dragstart="onTaskDragStart($event, t.id)"
            >
              <td class="px-4 py-3 w-8">
                <input
                  type="checkbox"
                  :checked="selected.has(t.id)"
                  :disabled="!canSelect(t)"
                  class="rounded disabled:opacity-30"
                  @change="toggleOne(t.id)"
                />
              </td>
              <td class="px-4 py-3 font-medium text-slate-900">{{ t.name }}</td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span :class="['px-2 py-0.5 rounded-full text-xs', statusClass[t.status]]">
                  {{ statusLabel[t.status] }}
                </span>
                <!-- 失败原因 tooltip -->
                <span
                  v-if="t.status === 'failed' && t.meta?.error"
                  class="relative group ml-1.5 inline-flex items-center"
                >
                  <svg class="w-3.5 h-3.5 text-rose-400 cursor-help" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="absolute left-0 bottom-full mb-1.5 hidden group-hover:block z-20 w-56 bg-slate-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg leading-relaxed pointer-events-none">
                    {{ parseTaskError(t.meta?.error).friendly }}
                    <br>
                    <span class="text-slate-300 mt-0.5 block">{{ parseTaskError(t.meta?.error).suggestion }}</span>
                  </span>
                </span>
              </td>
              <td class="px-4 py-3 text-slate-600">{{ t.current_stage || '—' }}</td>
              <td class="px-4 py-3 text-slate-500 whitespace-nowrap">{{ fmtDate(t.created_at) }}</td>
              <td class="px-4 py-3 text-slate-500 whitespace-nowrap">{{ fmtDate(t.updated_at) }}</td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button
                  v-if="canResume(t)"
                  class="text-slate-700 hover:text-slate-900 underline mr-3 disabled:opacity-50"
                  :disabled="!!actionBusy[t.id]"
                  @click="resumeTask(t)"
                >
                  {{ actionBusy[t.id] ? '继续生成中...' : '继续生成' }}
                </button>
                <router-link
                  :to="`/teacher/tasks/${t.id}`"
                  class="text-slate-700 hover:text-slate-900 underline"
                >查看</router-link>
                <button
                  class="text-rose-500 hover:text-rose-700 underline ml-3 disabled:opacity-50"
                  :disabled="!!actionBusy[t.id] || singleDeleting"
                  @click="deleteTask(t)"
                >
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 提示文字 -->
      <p class="mt-3 text-xs text-slate-400">
        拖拽任务行到左侧文件夹可归类。
      </p>
    </div>

  </div>

  <!-- 单条删除确认弹窗 -->
  <Teleport to="body">
    <div v-if="confirmDeleteTask" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
        <h3 class="text-base font-semibold text-slate-900 mb-2">确认删除任务</h3>
        <p class="text-sm text-slate-600 mb-1">
          将永久删除任务 <span class="font-medium">{{ confirmDeleteTask.name }}</span>。
        </p>
        <p class="text-sm text-rose-600 mb-4">此操作不可撤销，上传的 PDF 与所有生成数据将一并删除。</p>
        <div class="flex justify-end gap-2">
          <button
            class="px-4 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
            :disabled="singleDeleting"
            @click="confirmDeleteTask = null"
          >取消</button>
          <button
            class="px-4 py-2 text-sm rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50"
            :disabled="singleDeleting"
            @click="confirmDeleteOne"
          >{{ singleDeleting ? '删除中...' : '确认删除' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
