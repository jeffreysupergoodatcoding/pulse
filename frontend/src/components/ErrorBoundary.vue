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
  background: #0d1117; border: 1px solid #450a0a; border-radius: 8px;
}
.error-icon  { font-size: 32px; color: #f87171; }
.error-title { font-size: 15px; font-weight: 600; color: #f87171; }
.error-message { font-size: 12px; color: #64748b; text-align: center; max-width: 400px; font-family: monospace; }
</style>
