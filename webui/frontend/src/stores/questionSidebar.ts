import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Question } from '@/types/pipeline';

export const useQuestionSidebar = defineStore('questionSidebar', () => {
  const openState = ref(false);
  const question = ref<Question | null>(null);

  function open(q: Question) {
    question.value = q;
    openState.value = true;
  }

  function close() {
    openState.value = false;
    question.value = null;
  }

  return {
    openState,
    question,
    open,
    close,
  };
});
