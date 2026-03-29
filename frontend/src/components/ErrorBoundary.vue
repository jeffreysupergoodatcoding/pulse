<template>
  <div v-if="error" class="error-boundary">
    <div class="error-icon">⚠</div>
    <div class="error-title">Something went wrong</div>
    <div class="error-message">{{ errorMessage }}</div>
    <button class="btn btn-secondary btn-sm" @click="reset">Try again</button>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'

const error = ref(null)
const errorMessage = ref('')

onErrorCaptured((err) => {
  error.value = err
  errorMessage.value = err?.message || String(err)
  // Prevent propagation — boundary handles it
  return false
})

function reset() {
  error.value = null
  errorMessage.value = ''
}
</script>

<style scoped>
.error-boundary {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px; gap: 10px; padding: 32px;
  background: var(--negative-bg);
  border: 1px solid rgba(220, 38, 38, 0.2);
  border-radius: var(--radius-lg);
}
.error-icon  { font-size: 32px; color: var(--negative); }
.error-title { font-size: 15px; font-weight: 600; color: var(--negative-text); }
.error-message { font-size: 12px; color: var(--text-muted); text-align: center; max-width: 400px; font-family: var(--font-mono); }
</style>
