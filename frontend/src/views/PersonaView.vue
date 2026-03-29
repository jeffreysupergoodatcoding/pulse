<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">
          Persona Archetypes
          <span v-if="archetypes.length" class="persona-count">{{ archetypes.length }}</span>
        </h1>
        <p class="view-subtitle">AI-generated community profiles from ingested content</p>
      </div>
      <div class="flex gap-2" style="align-items:center">
        <select v-model="selectedTemplate" style="width:180px">
          <option value="">— From template —</option>
          <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
        <button class="btn btn-secondary btn-sm" :disabled="!selectedTemplate || generating" @click="fromTemplate">
          Use Template
        </button>
        <button class="btn btn-primary btn-sm" :disabled="generating" @click="generate">
          {{ generating ? 'Generating…' : '⟳ Generate' }}
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
      No personas generated yet. Click <strong>Generate</strong> to create archetypes from corpus.
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
const templates = ref([])
const selectedTemplate = ref('')
const generating = ref(false)
const taskId = ref('')
const taskStatus = ref('')
const progress = ref(0)
let pollTimer = null

async function loadSets() {
  try {
    const r = await personaApi.getSets(entityId)
    const sets = r.data.persona_sets || r.data || []
    if (sets.length) {
      const latest = sets[sets.length - 1]
      archetypes.value = latest.archetypes || []
    }
  } catch { /* ignore */ }
}

async function loadTemplates() {
  try {
    const r = await personaApi.getTemplates()
    templates.value = r.data.templates || r.data || []
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

async function fromTemplate() {
  generating.value = true
  try {
    const r = await personaApi.fromTemplate({ entity_id: entityId, template_id: selectedTemplate.value })
    archetypes.value = r.data.archetypes || []
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    generating.value = false
  }
}

function pollProgress() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!taskId.value) return
    const r = await personaApi.getStatus(taskId.value)
    taskStatus.value = r.data.status
    progress.value = r.data.progress || 0
    if (['completed', 'error'].includes(r.data.status)) {
      clearInterval(pollTimer)
      generating.value = false
      if (r.data.status === 'completed') loadSets()
    }
  }, 1500)
}

onMounted(() => { loadSets(); loadTemplates() })
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
