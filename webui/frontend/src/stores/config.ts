import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getConfig, saveConfig, loadPreset } from '@/api/config';
import type { EduConfig } from '@/types/config';

export const useConfigStore = defineStore('config', () => {
  const config = ref<EduConfig>({
    taxonomy: [],
    question_types: [],
    ability_levels: [],
    operators: {},
  });
  const errors = ref<string[]>([]);
  const loading = ref(false);
  const saving = ref(false);

  async function load() {
    loading.value = true;
    errors.value = [];
    try {
      config.value = await getConfig();
    } catch (e) {
      errors.value = [e instanceof Error ? e.message : '加载失败'];
    } finally {
      loading.value = false;
    }
  }

  async function save(): Promise<boolean> {
    saving.value = true;
    errors.value = [];
    try {
      const result = await saveConfig(config.value);
      if (result.ok) return true;
      errors.value = result.errors || ['保存失败'];
      return false;
    } catch (e) {
      errors.value = [e instanceof Error ? e.message : '保存失败'];
      return false;
    } finally {
      saving.value = false;
    }
  }

  async function loadPresetConfig(name: string): Promise<boolean> {
    loading.value = true;
    errors.value = [];
    try {
      config.value = await loadPreset(name);
      return true;
    } catch (e) {
      errors.value = [e instanceof Error ? e.message : '加载预设失败'];
      return false;
    } finally {
      loading.value = false;
    }
  }

  function setConfig(c: EduConfig) {
    config.value = c;
  }

  function clearErrors() {
    errors.value = [];
  }

  return {
    config,
    errors,
    loading,
    saving,
    load,
    save,
    loadPresetConfig,
    setConfig,
    clearErrors,
  };
});
