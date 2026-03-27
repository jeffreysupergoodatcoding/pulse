<template>
  <div>
    <div class="flex" style="align-items:center;justify-content:space-between;margin-bottom:20px">
      <div class="section-title" style="margin-bottom:0">Simulation — {{ entityId }}</div>
      <div class="flex gap-2">
        <button v-if="!simId" class="btn btn-primary" :disabled="creating" @click="createSim">
          {{ creating ? 'Creating…' : 'New Simulation' }}
        </button>
        <template v-else>
          <span class="text-muted" style="font-size:12px;align-self:center">{{ simId.slice(0,8) }}</span>
          <button v-if="status.status !== 'running'" class="btn btn-primary btn-sm" :disabled="starting" @click="startSim">
            {{ starting ? 'Starting…' : '▶ Start' }}
          </button>
          <button v-else class="btn btn-danger btn-sm" @click="stopSim">■ Stop</button>
          <button v-if="status.status === 'completed'" class="btn btn-secondary btn-sm" @click="generateReport">
            Generate Report →
          </button>
        </template>
      </div>
    </div>

    <!-- Config form (only before sim created) -->
    <div v-if="!simId" class="card" style="max-width:560px;margin-bottom:20px">
      <div class="grid-2">
        <div>
          <label>Rounds</label>
          <input v-model.number="config.rounds" type="number" min="1" max="100" />
        </div>
        <div>
          <label>Agents</label>
          <input v-model.number="config.n_agents" type="number" min="5" max="500" />
        </div>
      </div>
      <div class="mt-3">
        <label>Hypothetical event (optional)</label>
        <textarea v-model="config.hypothetical_event" rows="2" placeholder="What if Nike launched a new collab…" />
      </div>
    </div>

    <!-- Inject event (while running) -->
    <div v-if="simId && status.status === 'running'" class="card" style="max-width:560px;margin-bottom:20px">
      <div style="font-size:13px;font-weight:600;margin-bottom:10px">Inject Event</div>
      <div class="flex gap-2">
        <input v-model="injectText" placeholder="Breaking: Nike drops new collection…" />
        <button class="btn btn-secondary btn-sm" :disabled="!injectText" @click="inject">Inject</button>
      </div>
    </div>

    <!-- Monitor + Chart -->
    <div v-if="simId">
      <SimulationMonitor :actions="actions" :status="status" />

      <div v-if="sentimentData.sentiment_by_round?.length" class="card mt-4">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px">Sentiment Over Time</div>
        <SentimentChart
          :sentiment-by-round="sentimentData.sentiment_by_round"
          :trajectory="prediction.trajectory"
        />
        <div v-if="prediction.trajectory?.direction" class="mt-2 flex gap-3">
          <div class="stat">
            <span class="text-muted">Trend</span>
            <strong>{{ prediction.trajectory.direction }}</strong>
          </div>
          <div class="stat">
            <span class="text-muted">Forecast</span>
            <strong>{{ prediction.trajectory.predicted_final_score?.toFixed(3) }}</strong>
          </div>
          <div class="stat">
            <span class="text-muted">Confidence</span>
            <strong>{{ (prediction.trajectory.confidence * 100).toFixed(0) }}%</strong>
          </div>
        </div>
      </div>

      <!-- Report link after completion -->
      <div v-if="reportId" class="card mt-4" style="max-width:400px">
        <div style="font-size:13px;font-weight:600;margin-bottom:8px">Report</div>
        <div class="text-muted" style="font-size:12px;margin-bottom:10px">
          Report ID: {{ reportId }} · Status: {{ reportStatus }}
        </div>
        <router-link
          v-if="reportStatus === 'completed'"
          :to="`/entity/${entityId}/report/${reportId}`"
          class="btn btn-primary btn-sm"
        >View Report →</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { simulation as simApi } from '../api/simulation.js'
import { report as reportApi } from '../api/report.js'
import SimulationMonitor from '../components/SimulationMonitor.vue'
import SentimentChart from '../components/SentimentChart.vue'

const route = useRoute()
const entityId = route.params.id

const simId = ref('')
const status = ref({})
const actions = ref([])
const sentimentData = ref({})
const prediction = ref({})
const creating = ref(false)
const starting = ref(false)
const injectText = ref('')
const reportId = ref('')
const reportStatus = ref('')
let pollTimer = null

const config = ref({ rounds: 10, n_agents: 20, hypothetical_event: '' })

async function createSim() {
  creating.value = true
  try {
    const r = await simApi.create({
      entity_id: entityId,
      rounds: config.value.rounds,
      n_agents: config.value.n_agents,
    })
    simId.value = r.data.simulation_id
    startPolling()
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    creating.value = false
  }
}

async function startSim() {
  starting.value = true
  try {
    await simApi.start(simId.value, {
      hypothetical_event: config.value.hypothetical_event || undefined,
    })
    startPolling()
  } finally {
    starting.value = false
  }
}

async function stopSim() {
  await simApi.stop(simId.value)
}

async function inject() {
  if (!injectText.value) return
  await simApi.inject(simId.value, {
    event_text: injectText.value,
    round: (status.value.current_round || 0) + 1,
  })
  injectText.value = ''
}

async function generateReport() {
  const r = await reportApi.generate(simId.value)
  reportId.value = r.data.report_id
  reportStatus.value = 'running'
  pollReport()
}

function pollReport() {
  const t = setInterval(async () => {
    const r = await reportApi.getStatus(reportId.value)
    reportStatus.value = r.data.status
    if (['completed', 'error'].includes(r.data.status)) clearInterval(t)
  }, 2000)
}

function startPolling() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!simId.value) return
    try {
      const [sR, aR] = await Promise.all([
        simApi.getStatus(simId.value),
        simApi.getActions(simId.value, { limit: 200 }),
      ])
      status.value = sR.data
      actions.value = (aR.data.actions || aR.data || []).slice(-100)

      if (sR.data.status === 'completed' || sR.data.actions_count > 0) {
        const [sentR, predR] = await Promise.allSettled([
          simApi.getSentiment(simId.value),
          simApi.getPrediction(simId.value),
        ])
        if (sentR.status === 'fulfilled') sentimentData.value = sentR.value.data
        if (predR.status === 'fulfilled') prediction.value = predR.value.data
      }

      if (sR.data.status === 'completed') clearInterval(pollTimer)
    } catch { /* ignore */ }
  }, 2000)
}

onMounted(() => {
  // Try to resume from localStorage
  const saved = localStorage.getItem(`sim_${entityId}`)
  if (saved) {
    simId.value = saved
    startPolling()
  }
})

// Persist simId
import { watch } from 'vue'
watch(simId, v => {
  if (v) localStorage.setItem(`sim_${entityId}`, v)
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.stat { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.stat span { font-size: 11px; }
textarea { resize: vertical; }
</style>
