<template>
  <div>
    <div class="flex" style="align-items:center;justify-content:space-between;margin-bottom:20px">
      <div class="section-title" style="margin-bottom:0">Persona Archetypes — {{ entityId }}</div>
      <div class="flex gap-2">
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

    <div v-if="taskId" class="card mb-4" style="max-width:400px;margin-bottom:16px">
      <div class="text-muted" style="font-size:12px">Task: {{ taskId }} — {{ taskStatus }}</div>
      <div class="progress-bar mt-2">
        <div class="progress-fill" :style="{ width: (progress || 5) + '%' }" />
      </div>
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
.progress-bar { height: 4px; background: var(--bg-overlay); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); transition: width .4s; }
</style>
