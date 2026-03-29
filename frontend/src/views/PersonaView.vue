<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">
          Persona Archetypes
          <span v-if="archetypes.length" class="persona-count">{{ archetypes.length }}</span>
        </h1>
        <p class="view-subtitle">AI-generated community profiles from knowledge graph</p>
      </div>
      <div class="flex gap-2" style="align-items:center">
        <button class="btn btn-primary btn-sm" :disabled="generating" @click="generate">
          {{ generating ? 'Generating…' : '⟳ Generate from Graph' }}
        </button>
      </div>
    </div>

    <!-- Slim progress bar -->
    <div v-if="taskId" class="persona-progress-wrap">
      <div class="persona-progress-bar" :style="{ width: (progress || 5) + '%' }" />
    </div>

    <div v-if="archetypes.length" class="grid-3">
      <PersonaCard v-for="a in archetypes" :key="a.archetype_id || a.id" :archetype="a" />
    </div>
    <div v-else-if="!generating" class="text-muted">
      No personas generated yet. Build the knowledge graph first, then click <strong>Generate from Graph</strong>.
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { persona as personaApi } from '../api/persona.js'
import PersonaCard from '../components/PersonaCard.vue'

const route = useRoute()
const entityId = route.params.id
const archetypes = ref([])
const generating = ref(false)
const taskId = ref('')
const taskStatus = ref('')
const progress = ref(0)
let pollTimer = null

async function loadSets() {
  try {
    const r = await personaApi.getSets(entityId)
    const sets = r.data.persona_sets || r.data || []
    if (!sets.length) return
    // Sort by created_at descending and take the latest
    const sorted = [...sets].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    const latest = sorted[0]
    const setId = latest.set_id || latest.id
    if (!setId) return
    const full = await personaApi.getSet(entityId, setId)
    archetypes.value = full.data.archetypes || []
  } catch { /* ignore */ }
}

async function generate() {
  generating.value = true
  taskId.value = ''
  try {
    const r = await personaApi.generate({ entity_id: entityId })
    taskId.value = r.data.task_id
    pollProgress()
  } catch (e) {
    alert(e.response?.data?.error || e.message)
    generating.value = false
  }
}

function pollProgress() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!taskId.value) return
    try {
      const r = await personaApi.getStatus(taskId.value)
      taskStatus.value = r.data.status
      progress.value = r.data.progress || 0
      if (['completed', 'error'].includes(r.data.status)) {
        clearInterval(pollTimer)
        generating.value = false
        if (r.data.status === 'completed') loadSets()
      }
    } catch {
      // Network error — keep polling, don't get stuck
    }
  }, 1500)
}

onMounted(() => { loadSets() })
</script>

<style scoped>
.persona-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-muted);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
  border-radius: var(--radius-full);
  padding: 0 8px;
  height: 20px;
  vertical-align: middle;
  margin-left: 8px;
}
.persona-progress-wrap {
  height: 3px;
  background: var(--bg-overlay);
  margin: -24px -24px 16px;
  overflow: hidden;
}
.persona-progress-bar {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s;
}
</style>
