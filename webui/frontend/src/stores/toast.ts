import { defineStore } from 'pinia';
import { ref } from 'vue';

export type ToastType = 'info' | 'warning' | 'success';

export const useToastStore = defineStore('toast', () => {
  const items = ref<Array<{ id: number; message: string; type: ToastType }>>([]);
  let nextId = 0;
  function show(message: string, type: ToastType = 'info') {
    const id = nextId++;
    items.value.push({ id, message, type });
    setTimeout(() => {
      items.value = items.value.filter((t) => t.id !== id);
    }, 4000);
  }

  function remove(id: number) {
    items.value = items.value.filter((t) => t.id !== id);
  }

  return { items, show, remove };
});
