<template>
  <div class="sim-view">

    <!-- ── WIZARD (pre-launch) ─────────────────────────── -->
    <div v-if="!simId" class="sim-wizard">
      <!-- Wizard header with step progress -->
      <div class="wiz-header">
        <div class="wiz-steps">
          <div
            v-for="s in wizardSteps"
            :key="s.n"
            class="wiz-step"
            :class="{ active: wizardStep === s.n, done: wizardStep > s.n }"
          >
            <div class="wiz-step-num">{{ wizardStep > s.n ? '✓' : s.n }}</div>
            <div class="wiz-step-label">{{ s.label }}</div>
          </div>
        </div>
      </div>

      <!-- Scrollable content: wizard panel + history -->
      <div class="wiz-body">

        <!-- Step 1: Scenario & Stimuli -->
        <div v-if="wizardStep === 1" class="wiz-panel">
          <div class="wiz-panel-num">01</div>
          <div class="wiz-panel-title">Scenario & Stimuli</div>
          <div class="wiz-panel-sub">Define what event or narrative to simulate</div>

          <div class="wiz-field">
            <label>Entity</label>
            <input type="text" :value="entityId" disabled style="opacity:0.6" />
          </div>

          <div class="wiz-field">
            <label>Narrative direction <span class="wiz-field-hint">— the event, rumor, or story to inject</span></label>
            <textarea
              v-model="config.hypothetical_event"
              rows="4"
              placeholder="e.g. Nike secretly launches a collaboration with a controversial artist, sparking debate across communities…"
            />
          </div>

          <div class="wiz-field">
            <label>Initial hot topics <span class="wiz-field-hint">— press Enter to add</span></label>
            <div class="wiz-tags" @click="topicInputRef?.focus()">
              <span v-for="(tag, i) in hotTopics" :key="i" class="wiz-tag">
                #{{ tag }}
                <button class="wiz-tag-rm" @click.stop="hotTopics.splice(i, 1)" aria-label="Remove topic">×</button>
              </span>
              <input
                ref="topicInputRef"
                v-model="topicInput"
                class="wiz-tag-input"
                placeholder="Add topic…"
                @keydown.enter.prevent="addTopic"
                @keydown.comma.prevent="addTopic"
              />
            </div>
          </div>

          <div class="wiz-actions">
            <button class="btn btn-primary" @click="wizardStep = 2">
              Next: Personas →
            </button>
          </div>
        </div>

        <!-- Step 2: Who to simulate -->
        <div v-if="wizardStep === 2" class="wiz-panel">
          <div class="wiz-panel-num">02</div>
          <div class="wiz-panel-title">Who to Simulate</div>
          <div class="wiz-panel-sub">Choose the population of agents for this simulation</div>

          <div class="wiz-field">
            <label>Persona source</label>
            <div class="wiz-note">
              Agents are generated from the knowledge graph. Run <strong>Generate from Graph</strong> on the Persona page first.
            </div>
          </div>

          <div class="wiz-field-row">
            <div class="wiz-field">
              <label>Agent count</label>
              <input v-model.number="config.n_agents" type="number" min="5" max="500" />
              <span class="wiz-field-hint">5 – 500 agents</span>
            </div>
            <div class="wiz-field">
              <label>Platform mix</label>
              <div class="wiz-platform-row">
                <label class="wiz-toggle" :class="{ on: platforms.twitter }">
                  <input type="checkbox" v-model="platforms.twitter" />
                  Twitter
                </label>
                <label class="wiz-toggle" :class="{ on: platforms.reddit }">
                  <input type="checkbox" v-model="platforms.reddit" />
                  Reddit
                </label>
              </div>
            </div>
          </div>

          <div class="wiz-actions">
            <button class="btn btn-secondary" @click="wizardStep = 1">← Back</button>
            <button class="btn btn-primary" @click="wizardStep = 3">Next: Config →</button>
          </div>
        </div>

        <!-- Step 3: Config & Launch -->
        <div v-if="wizardStep === 3" class="wiz-panel">
          <div class="wiz-panel-num">03</div>
          <div class="wiz-panel-title">Simulation Parameters</div>
          <div class="wiz-panel-sub">Final configuration before launch</div>

          <div class="wiz-field-row">
            <div class="wiz-field">
              <label>Rounds</label>
              <input v-model.number="config.rounds" type="number" min="1" max="100" />
              <span class="wiz-field-hint">1 – 100 rounds</span>
            </div>
            <div class="wiz-field">
              <label>Agents</label>
              <input :value="config.n_agents" disabled style="opacity:0.6" />
            </div>
          </div>

          <!-- Summary -->
          <div class="wiz-summary">
            <div class="wiz-summary-title">Simulation Summary</div>
            <div class="wiz-summary-row">
              <span>Narrative</span>
              <span>{{ config.hypothetical_event ? config.hypothetical_event.slice(0, 80) + (config.hypothetical_event.length > 80 ? '…' : '') : '(none)' }}</span>
            </div>
            <div class="wiz-summary-row" v-if="hotTopics.length">
              <span>Topics</span>
              <div class="wiz-summary-tags">
                <span v-for="t in hotTopics" :key="t" class="wiz-tag">#{{ t }}</span>
              </div>
            </div>
            <div class="wiz-summary-row">
              <span>Agents</span>
              <span>{{ config.n_agents }} agents · {{ config.rounds }} rounds</span>
            </div>
            <div class="wiz-summary-row">
              <span>Persona source</span>
              <span>Knowledge graph archetypes</span>
            </div>
          </div>

          <div class="wiz-actions">
            <button class="btn btn-secondary" @click="wizardStep = 2">← Back</button>
            <button class="btn btn-primary" :disabled="creating" @click="createAndStart">
              {{ creating ? 'Launching…' : '▶ Launch Simulation' }}
            </button>
          </div>
        </div>

        <!-- Past simulations -->
        <div v-if="historyList.length" class="sim-history">
          <div class="sim-history-title">Past Simulations</div>
          <div class="sim-history-list">
            <div
              v-for="h in historyList"
              :key="h.simulation_id"
              class="sim-history-item"
              @click="resumeSim(h.simulation_id)"
            >
              <span class="sim-history-id">{{ h.simulation_id.slice(0, 8) }}</span>
              <span class="status-pill" :class="'status-' + h.status">{{ h.status }}</span>
              <span class="sim-history-detail">{{ h.current_round }}/{{ h.total_rounds }} rounds</span>
              <span class="sim-history-detail">{{ h.actions_count }} actions</span>
              <span class="sim-history-date">{{ h.started_at ? new Date(h.started_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—' }}</span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ── RUNNING DASHBOARD ────────────────────────────── -->
    <template v-else>
      <!-- Control bar -->
      <div class="sim-controls">
        <span class="sim-id-chip">{{ simId.slice(0, 8) }}</span>
        <span class="status-pill" :class="`status-${status.status || 'idle'}`">
          {{ status.status || 'idle' }}
        </span>
        <div class="round-counter">
          Round
          <strong>{{ status.current_round || 0 }}</strong>
          <span class="round-total">/ {{ status.total_rounds || config.rounds }}</span>
        </div>
        <div class="ctrl-progress">
          <div
            class="ctrl-progress-bar"
            :style="{ width: progressPct + '%' }"
          />
        </div>

        <div class="ctrl-spacer" />

        <!-- Error message -->
        <span v-if="status.status === 'error'" class="sim-error-msg">
          Error: {{ status.error_message || 'Simulation failed' }}
        </span>

        <!-- Inject event (while running) -->
        <template v-if="status.status === 'running'">
          <input
            v-model="injectText"
            class="inject-input"
            placeholder="Inject event into simulation…"
            @keydown.enter="inject"
          />
          <button class="btn btn-secondary btn-sm" :disabled="!injectText" @click="inject">
            Inject
          </button>
        </template>

        <!-- Start / Stop -->
        <button
          v-if="status.status !== 'running'"
          class="btn btn-primary btn-sm"
          :disabled="starting || ['completed'].includes(status.status)"
          @click="startSim"
        >
          {{ starting ? 'Starting…' : status.status === 'completed' ? 'Completed' : status.status === 'error' ? '↺ Retry' : '▶ Start' }}
        </button>
        <button v-else class="btn btn-danger btn-sm" @click="stopSim">■ Stop</button>

        <button
          v-if="status.status === 'completed'"
          class="btn btn-secondary btn-sm"
          :disabled="reportStatus === 'running'"
          @click="generateReport"
        >
          {{ reportStatus === 'running' ? 'Generating…' : 'Generate Report →' }}
        </button>
        <button
          v-if="reportId && reportStatus === 'completed'"
          class="btn btn-primary btn-sm"
          @click="showReportModal = true"
        >View Report</button>

        <button
          v-if="['completed', 'stopped', 'error'].includes(status.status)"
          class="btn btn-secondary btn-sm"
          @click="newSimulation"
        >+ New Simulation</button>
      </div>

      <!-- Split pane body -->
      <div class="sim-body">

        <!-- Left: Agent network -->
        <div class="sim-pane-left" :style="{ flexBasis: splitX + '%' }">
          <div class="pane-header">Agent Network</div>
          <div class="sim-graph-wrap">
            <AgentNetworkGraph
              :sim-id="simId"
              :actions="actions"
              :running="status.status === 'running'"
            />
          </div>
        </div>

        <!-- Horizontal drag divider -->
        <div class="sim-divider-h" @mousedown="startDragH" />

        <!-- Right: Sentiment + Activity -->
        <div class="sim-pane-right" :style="{ flexBasis: (100 - splitX) + '%' }">

          <!-- Scenario info -->
          <div class="sim-scenario-bar" v-if="config.hypothetical_event">
            <div class="sim-scenario-label">Simulation Scenario</div>
            <div class="sim-scenario-text">{{ config.hypothetical_event }}</div>
            <div class="sim-topic-pills" v-if="hotTopics.length">
              <span v-for="t in hotTopics" :key="t" class="sim-topic-pill">#{{ t }}</span>
            </div>
          </div>

          <!-- Sentiment metrics -->
          <div class="sim-sentiment-section">
            <div class="pane-header">Sentiment Flow</div>

            <!-- Score + distribution row -->
            <div class="sim-metrics-row" v-if="latestSentiment !== null">
              <div class="sim-score-badge" :class="scoreClass">
                Overall Score: {{ latestSentiment?.toFixed(2) }}
                <span class="sim-score-label">{{ scoreLabel }}</span>
              </div>
              <div class="sim-distribution" v-if="distribution">
                <span class="dist-neg">{{ distribution.neg }}% Neg</span>
                <span class="dist-neu">{{ distribution.neu }}% Neu</span>
                <span class="dist-pos">{{ distribution.pos }}% Pos</span>
              </div>
            </div>

            <!-- Sentiment wave chart -->
            <div class="sim-chart-wrap">
              <SentimentChart
                v-if="sentimentData.sentiment_by_round?.length"
                :sentiment-by-round="sentimentData.sentiment_by_round"
                :trajectory="prediction.trajectory"
              />
              <div v-else class="sim-chart-empty">
                Sentiment wave will appear as simulation runs
              </div>
            </div>

            <!-- Trajectory stats -->
            <div v-if="prediction.trajectory?.direction" class="sim-traj-row">
              <div class="sim-traj-stat">
                <span>Trend</span>
                <strong>{{ prediction.trajectory.direction }}</strong>
              </div>
              <div class="sim-traj-stat">
                <span>Forecast</span>
                <strong>{{ prediction.trajectory.predicted_final_score?.toFixed(3) }}</strong>
              </div>
              <div class="sim-traj-stat">
                <span>Confidence</span>
                <strong>{{ (prediction.trajectory.confidence * 100).toFixed(0) }}%</strong>
              </div>
            </div>
          </div>

          <!-- Vertical drag divider above activity log -->
          <div class="sim-divider-v" @mousedown="startDragV" />

          <!-- Agent activity log -->
          <div class="sim-feed-section" :style="{ flexBasis: feedHeight + 'px' }">
            <div class="pane-header">Agent Activity Log</div>
            <div class="sim-feed-wrap">
              <SimulationMonitor :actions="actions" :status="status" />
            </div>
          </div>

        </div>
      </div>

      <!-- System console -->
      <SystemConsole :sim-id="simId" :actions="actions" :status="status" />
    </template>

    <!-- Report modal overlay -->
    <Teleport to="body">
      <div v-if="showReportModal" class="report-overlay" @click.self="showReportModal = false">
        <div class="report-modal">
          <div class="report-modal-header">
            <span class="report-modal-title">Simulation Report</span>
            <div class="report-modal-actions">
              <button class="btn btn-secondary btn-sm" @click="downloadPdf">
                Download PDF
              </button>
              <button class="report-modal-close" @click="showReportModal = false" aria-label="Close">×</button>
            </div>
          </div>
          <div class="report-modal-body" ref="reportContentRef">
            <div v-if="reportMarkdown" class="report-rendered" v-html="renderedReport"></div>
            <div v-else class="report-loading">Loading report…</div>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { simulation as simApi } from '../api/simulation.js'
import { report as reportApi } from '../api/report.js'
import SimulationMonitor from '../components/SimulationMonitor.vue'
import SentimentChart from '../components/SentimentChart.vue'
import AgentNetworkGraph from '../components/AgentNetworkGraph.vue'
import SystemConsole from '../components/SystemConsole.vue'

const route = useRoute()
const entityId = route.params.id

// Wizard state
const wizardStep = ref(1)
const wizardSteps = [
  { n: 1, label: 'Scenario' },
  { n: 2, label: 'Personas' },
  { n: 3, label: 'Config' },
]
const hotTopics = ref([])
const topicInput = ref('')
const topicInputRef = ref(null)
const platforms = ref({ twitter: true, reddit: true })

// Simulation state
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
const showReportModal = ref(false)
const reportMarkdown = ref('')
const reportContentRef = ref(null)
const historyList = ref([])
const historyLoading = ref(false)
let pollTimer = null

const config = ref({ rounds: 10, n_agents: 20, hypothetical_event: '' })

// ── Resizable pane state ──
const splitX = ref(58)       // horizontal split: left pane % width
const feedHeight = ref(200)  // activity log height in px
let dragType = null
let dragStartPos = 0
let dragStartVal = 0
let bodyEl = null

function startDragH(e) {
  e.preventDefault()
  dragType = 'h'
  dragStartPos = e.clientX
  dragStartVal = splitX.value
  bodyEl = e.target.closest('.sim-body')
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
}

function startDragV(e) {
  e.preventDefault()
  dragType = 'v'
  dragStartPos = e.clientY
  dragStartVal = feedHeight.value
  bodyEl = e.target.closest('.sim-pane-right')
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'ns-resize'
  document.body.style.userSelect = 'none'
}

function onDrag(e) {
  if (dragType === 'h' && bodyEl) {
    const rect = bodyEl.getBoundingClientRect()
    const pct = ((e.clientX - rect.left) / rect.width) * 100
    splitX.value = Math.min(80, Math.max(25, pct))
  } else if (dragType === 'v') {
    const delta = dragStartPos - e.clientY
    feedHeight.value = Math.min(600, Math.max(80, dragStartVal + delta))
  }
}

function stopDrag() {
  dragType = null
  bodyEl = null
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// Computed
const progressPct = computed(() => {
  const cur = status.value.current_round || 0
  const tot = status.value.total_rounds || config.value.rounds || 1
  return Math.min((cur / tot) * 100, 100)
})

const latestSentiment = computed(() => {
  const rounds = sentimentData.value.sentiment_by_round
  if (!rounds?.length) return null
  return rounds[rounds.length - 1]?.mean_score ?? null
})

const scoreClass = computed(() => {
  const s = latestSentiment.value
  if (s === null) return ''
  if (s > 0.2) return 'score-positive'
  if (s < -0.2) return 'score-negative'
  return 'score-neutral'
})

const scoreLabel = computed(() => {
  const s = latestSentiment.value
  if (s === null) return ''
  if (s > 0.5) return '(Highly Positive)'
  if (s > 0.2) return '(Positive)'
  if (s < -0.5) return '(Highly Negative)'
  if (s < -0.2) return '(Negative)'
  return '(Neutral)'
})

const distribution = computed(() => {
  const rounds = sentimentData.value.sentiment_by_round
  if (!rounds?.length) return null
  const all = rounds.flatMap(r => Array(r.count).fill(r.mean_score))
  if (!all.length) return null
  const pos = all.filter(s => s > 0.1).length
  const neg = all.filter(s => s < -0.1).length
  const neu = all.length - pos - neg
  const total = all.length
  return {
    pos: Math.round((pos / total) * 100),
    neg: Math.round((neg / total) * 100),
    neu: Math.round((neu / total) * 100),
  }
})

// Wizard helpers
function addTopic() {
  const t = topicInput.value.trim().replace(/^#/, '')
  if (t && !hotTopics.value.includes(t)) hotTopics.value.push(t)
  topicInput.value = ''
}

// Simulation actions
async function createAndStart() {
  creating.value = true
  try {
    const payload = {
      entity_id: entityId,
      rounds: config.value.rounds,
      n_agents: config.value.n_agents,
    }
    const r = await simApi.create(payload)
    simId.value = r.data.simulation_id
    // Optimistically show running state so the Start button doesn't appear
    status.value = { status: 'running', current_round: 0, total_rounds: config.value.rounds }
    await simApi.start(simId.value, {
      hypothetical_event: config.value.hypothetical_event || undefined,
    })
    startPolling()
  } catch (e) {
    simId.value = ''
    status.value = {}
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
    status.value = { ...status.value, status: 'running' }
    startPolling()
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    starting.value = false
  }
}

async function stopSim() {
  try {
    await simApi.stop(simId.value)
    clearInterval(pollTimer)
    status.value = { ...status.value, status: 'stopped' }
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  }
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
  try {
    reportStatus.value = 'running'
    reportMarkdown.value = ''
    const r = await reportApi.generate(simId.value)
    reportId.value = r.data.report_id
    pollReport()
  } catch (e) {
    reportStatus.value = ''
    alert(e.response?.data?.error || e.message)
  }
}

function pollReport() {
  const t = setInterval(async () => {
    try {
      const r = await reportApi.getStatus(reportId.value)
      reportStatus.value = r.data.status
      if (r.data.status === 'completed') {
        clearInterval(t)
        await loadReportContent()
        showReportModal.value = true
      } else if (r.data.status === 'error') {
        clearInterval(t)
        alert('Report generation failed: ' + (r.data.error || 'unknown error'))
      }
    } catch { /* keep polling */ }
  }, 2000)
}

async function loadReportContent() {
  if (!reportId.value) return
  try {
    const r = await reportApi.getContent(reportId.value)
    reportMarkdown.value = r.data.markdown || ''
  } catch { /* ignore */ }
}

const renderedReport = computed(() => {
  if (!reportMarkdown.value) return ''
  return marked(reportMarkdown.value)
})

function downloadPdf() {
  const printWindow = window.open('', '_blank')
  if (!printWindow) return
  printWindow.document.write(`<!DOCTYPE html>
<html><head>
<title>Simulation Report</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1a1a2e; line-height: 1.6; font-size: 14px; }
  h1 { font-size: 24px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
  h2 { font-size: 18px; margin-top: 28px; color: #111827; }
  h3 { font-size: 15px; color: #374151; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; font-size: 13px; }
  th { background: #f9fafb; font-weight: 600; }
  code { background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 12px; }
  pre { background: #f3f4f6; padding: 12px; border-radius: 6px; overflow-x: auto; }
  blockquote { border-left: 3px solid #d1d5db; margin: 12px 0; padding: 8px 16px; color: #6b7280; }
  ul, ol { padding-left: 24px; }
  @media print { body { margin: 20px; } }
</style>
</head><body>${renderedReport.value}</body></html>`)
  printWindow.document.close()
  setTimeout(() => { printWindow.print() }, 300)
}

async function pollOnce() {
  if (!simId.value) return
  try {
    const [sR, aR] = await Promise.all([
      simApi.getStatus(simId.value),
      simApi.getActions(simId.value, { limit: 200 }),
    ])

    // Detect zombie: backend says running but subprocess is dead
    const isZombie = sR.data.status === 'running' && sR.data.subprocess_running === false && !sR.data.completed_at
    if (isZombie) {
      status.value = { ...sR.data, status: 'error', error_message: 'Simulation process died unexpectedly. Start a new simulation.' }
      clearInterval(pollTimer)
      return
    }

    // Don't downgrade optimistic 'running' to 'idle' while subprocess is still booting
    if (status.value.status === 'running' && sR.data.status === 'idle') {
      sR.data.status = 'running'
    }
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
  } catch (e) {
    // If the simulation no longer exists on the backend, clear stale state
    if (e.response?.status === 404) {
      clearInterval(pollTimer)
      localStorage.removeItem(`sim_${entityId}`)
      simId.value = ''
      status.value = {}
    }
    // All other errors: silently ignore (transient network issues)
  }
}

watch(showReportModal, async (open) => {
  if (open && reportId.value && !reportMarkdown.value) {
    await loadReportContent()
  }
})

function startPolling() {
  clearInterval(pollTimer)
  pollOnce() // fire immediately, don't wait 2s
  pollTimer = setInterval(pollOnce, 2000)
}

function newSimulation() {
  clearInterval(pollTimer)
  localStorage.removeItem(`sim_${entityId}`)
  simId.value = ''
  status.value = {}
  actions.value = []
  sentimentData.value = {}
  prediction.value = {}
  reportId.value = ''
  reportStatus.value = ''
  reportMarkdown.value = ''
  wizardStep.value = 1
  loadHistory()
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const r = await simApi.list(entityId)
    historyList.value = r.data.simulations || []
  } catch { /* ignore */ }
  finally { historyLoading.value = false }
}

function resumeSim(id) {
  simId.value = id
  localStorage.setItem(`sim_${entityId}`, id)
  actions.value = []
  sentimentData.value = {}
  prediction.value = {}
  reportId.value = ''
  reportStatus.value = ''
  reportMarkdown.value = ''
  startPolling()
}

// Persist simId
watch(simId, v => {
  if (v) localStorage.setItem(`sim_${entityId}`, v)
})

onMounted(async () => {
  // Try to resume from localStorage
  const saved = localStorage.getItem(`sim_${entityId}`)
  if (saved) {
    simId.value = saved
    startPolling()
  }
  // Load history
  await loadHistory()
})

onUnmounted(() => {
  clearInterval(pollTimer)
  stopDrag()
})
</script>

<style scoped>
/* ── View root ─────────────────────────────────── */
.sim-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg-canvas);
  font-family: var(--font-sans);
}

/* ── Wizard ────────────────────────────────────── */
.sim-wizard {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-canvas);
  position: relative;
}

/* Dot grid on wizard background */
.sim-wizard::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: radial-gradient(circle, rgba(0,0,0,0.07) 1px, transparent 1px);
  background-size: 22px 22px;
  z-index: 0;
}

.wiz-header {
  padding: 0 32px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.wiz-steps {
  display: flex;
  gap: 0;
  height: 52px;
  align-items: stretch;
}

.wiz-step {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 20px 0 0;
  opacity: 0.4;
  position: relative;
  cursor: default;
}
.wiz-step::after {
  content: '›';
  position: absolute;
  right: 4px;
  color: var(--border-default);
  font-size: 14px;
  top: 50%;
  transform: translateY(-50%);
}
.wiz-step:last-child::after { display: none; }
.wiz-step.active { opacity: 1; }
.wiz-step.done { opacity: 0.65; }

.wiz-step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-overlay);
  border: 1px solid var(--border-default);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-family: var(--font-sans);
}
.wiz-step.active .wiz-step-num {
  background: var(--text-primary);
  border-color: var(--text-primary);
  color: #fff;
}
.wiz-step.done .wiz-step-num {
  background: var(--positive);
  border-color: var(--positive);
  color: #fff;
}
.wiz-step-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  white-space: nowrap;
  letter-spacing: -0.1px;
}
.wiz-step.active .wiz-step-label { color: var(--text-primary); font-weight: 600; }

.wiz-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 24px;
  overflow-y: auto;
  position: relative;
  z-index: 1;
  gap: 32px;
}

.wiz-panel {
  width: 100%;
  max-width: 580px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: 36px 40px;
  box-shadow: var(--shadow-lg);
}

.wiz-panel-num {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-faint);
  letter-spacing: 1.2px;
  text-transform: uppercase;
  margin-bottom: 8px;
  font-family: var(--font-sans);
}
.wiz-panel-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
  letter-spacing: -0.5px;
  line-height: 1.2;
}
.wiz-panel-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 28px;
  line-height: 1.5;
}

.wiz-field { margin-bottom: 20px; }
.wiz-field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
  letter-spacing: 0.1px;
}
.wiz-field-hint {
  font-weight: 400;
  color: var(--text-faint);
  font-size: 11px;
  display: inline;
}
.wiz-note {
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  line-height: 1.5;
}

.wiz-field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

/* Tags / topics */
.wiz-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  min-height: 44px;
  align-items: center;
  cursor: text;
  transition: border-color var(--transition-fast);
}
.wiz-tags:focus-within {
  border-color: var(--text-primary);
  box-shadow: var(--shadow-focus);
}
.wiz-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  letter-spacing: 0;
}
.wiz-tag-rm {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-faint);
  font-size: 14px;
  line-height: 1;
  padding: 0 1px;
  display: flex;
  align-items: center;
  opacity: 0.7;
  transition: opacity var(--transition-fast), color var(--transition-fast);
}
.wiz-tag-rm:hover { opacity: 1; color: var(--negative); }
.wiz-tag-input {
  border: none !important;
  background: none !important;
  outline: none !important;
  box-shadow: none !important;
  font-size: 12px;
  color: var(--text-primary);
  padding: 0;
  width: 120px;
  min-width: 80px;
  font-family: var(--font-sans);
}

/* Radio group */
.wiz-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wiz-radio {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast);
  user-select: none;
}
.wiz-radio:hover { border-color: var(--border-default); background: var(--bg-hover); }
.wiz-radio.selected {
  border-color: var(--text-primary);
  background: var(--bg-overlay);
}
.wiz-radio input[type="radio"] {
  width: 15px;
  min-width: 15px;
  height: 15px;
  margin-top: 2px;
  accent-color: var(--text-primary);
}
.wiz-radio-label { display: flex; flex-direction: column; gap: 2px; }
.wiz-radio-label strong { font-size: 13px; color: var(--text-primary); font-weight: 600; letter-spacing: -0.2px; }
.wiz-radio-label span { font-size: 12px; color: var(--text-muted); }

/* Platform toggles */
.wiz-platform-row { display: flex; gap: 8px; flex-wrap: wrap; }
.wiz-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  user-select: none;
  letter-spacing: -0.1px;
}
.wiz-toggle input { display: none; }
.wiz-toggle.on {
  border-color: var(--text-primary);
  background: var(--text-primary);
  color: #FFFFFF;
}

/* Summary */
.wiz-summary {
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 20px;
}
.wiz-summary-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-faint);
  margin-bottom: 12px;
}
.wiz-summary-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-subtle);
  align-items: flex-start;
}
.wiz-summary-row:last-child { border-bottom: none; padding-bottom: 0; }
.wiz-summary-row > span:first-child {
  width: 120px;
  flex-shrink: 0;
  color: var(--text-faint);
  font-size: 12px;
}
.wiz-summary-tags { display: flex; flex-wrap: wrap; gap: 4px; }

.wiz-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border-subtle);
}

/* ── Simulation history ──────────────────────────── */
.sim-history {
  width: 100%;
  max-width: 580px;
}
.sim-history-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--text-faint);
  margin-bottom: 10px;
  font-family: var(--font-sans);
}
.sim-history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sim-history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast);
}
.sim-history-item:hover {
  border-color: var(--border-strong);
  background: var(--bg-hover);
  box-shadow: var(--shadow-sm);
}
.sim-history-id {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.sim-history-detail {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}
.sim-history-date {
  font-size: 11px;
  color: var(--text-faint);
  margin-left: auto;
  white-space: nowrap;
}

/* ── Control bar ────────────────────────────────── */
.sim-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  height: 48px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  flex-wrap: nowrap;
  overflow: hidden;
}
.sim-id-chip {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-faint);
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  letter-spacing: 0;
}
.round-counter {
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-family: var(--font-sans);
}
.round-counter strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.round-total { color: var(--text-faint); font-size: 12px; }
.ctrl-progress {
  width: 72px;
  height: 3px;
  background: var(--bg-overlay);
  border-radius: var(--radius-full);
  overflow: hidden;
  flex-shrink: 0;
}
.sim-error-msg {
  font-size: 12px;
  color: #f87171;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}
.ctrl-progress-bar {
  height: 100%;
  background: var(--text-primary);
  border-radius: var(--radius-full);
  transition: width 0.5s ease;
}
.ctrl-spacer { flex: 1; }
.inject-input {
  width: 220px;
  padding: 5px 10px;
  font-size: 12px;
  font-family: var(--font-sans);
}

/* ── Split pane body ────────────────────────────── */
.sim-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.sim-pane-left {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: #FFFFFF;
  position: relative;
  flex-shrink: 0;
}

/* Horizontal divider between left/right panes */
.sim-divider-h {
  width: 5px;
  cursor: ew-resize;
  background: var(--border-subtle);
  flex-shrink: 0;
  position: relative;
  z-index: 5;
  transition: background 0.15s;
}
.sim-divider-h:hover,
.sim-divider-h:active {
  background: var(--border-strong);
}

/* AgentNetworkGraph handles its own dot-grid internally */

.sim-graph-wrap {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  position: relative;
}

.sim-pane-right {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  background: var(--bg-surface);
}

/* Scenario bar */
.sim-scenario-bar {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-canvas);
  flex-shrink: 0;
}
.sim-scenario-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-faint);
  margin-bottom: 5px;
  font-family: var(--font-sans);
}
.sim-scenario-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 8px;
}
.sim-topic-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.sim-topic-pill {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-weight: 500;
  font-family: var(--font-mono);
}

/* Sentiment section — flexes to fill space above the activity log */
.sim-sentiment-section {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.sim-metrics-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px 10px;
  flex-wrap: wrap;
}
.sim-score-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-sans);
}
.score-positive { background: var(--positive-bg); color: var(--positive-text); }
.score-negative { background: var(--negative-bg); color: var(--negative-text); }
.score-neutral  { background: var(--neutral-bg); color: var(--neutral-text); }
.sim-score-label { font-weight: 400; opacity: 0.75; font-size: 11px; }

.sim-distribution {
  display: flex;
  gap: 8px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-sans);
}
.dist-neg { color: var(--negative); }
.dist-pos { color: var(--positive); }
.dist-neu { color: var(--text-muted); }

.sim-chart-wrap { padding: 0 16px 12px; }
.sim-chart-empty {
  padding: 18px 0;
  font-size: 12px;
  color: var(--text-faint);
  text-align: center;
  font-family: var(--font-sans);
}

.sim-traj-row {
  display: flex;
  gap: 6px;
  padding: 0 16px 14px;
}
.sim-traj-stat {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  padding: 6px 10px;
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  flex: 1;
  font-family: var(--font-sans);
}
.sim-traj-stat span { font-size: 10px; color: var(--text-faint); margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
.sim-traj-stat strong { color: var(--text-primary); font-weight: 600; letter-spacing: -0.2px; }

/* Vertical divider above activity log */
.sim-divider-v {
  height: 5px;
  cursor: ns-resize;
  background: var(--border-subtle);
  flex-shrink: 0;
  position: relative;
  z-index: 5;
  transition: background 0.15s;
}
.sim-divider-v:hover,
.sim-divider-v:active {
  background: var(--border-strong);
}

/* Feed section */
.sim-feed-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  flex-shrink: 0;
}
.sim-feed-wrap {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

textarea { resize: vertical; }

/* ── Report modal ─────────────────────────────── */
.report-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

.report-modal {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.2);
  width: 100%;
  max-width: 820px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.report-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.report-modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.report-modal-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.report-modal-close {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 18px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}
.report-modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.report-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
  min-height: 0;
}

.report-loading {
  text-align: center;
  color: var(--text-faint);
  font-size: 13px;
  padding: 40px 0;
}

/* Rendered markdown */
.report-rendered {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.7;
  font-family: var(--font-sans);
}
.report-rendered :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 16px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--border-subtle);
  letter-spacing: -0.5px;
}
.report-rendered :deep(h2) {
  font-size: 17px;
  font-weight: 700;
  margin: 28px 0 10px;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.report-rendered :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 20px 0 8px;
  color: var(--text-secondary);
}
.report-rendered :deep(p) {
  margin: 0 0 12px;
}
.report-rendered :deep(ul),
.report-rendered :deep(ol) {
  margin: 0 0 12px;
  padding-left: 22px;
}
.report-rendered :deep(li) {
  margin-bottom: 4px;
}
.report-rendered :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 13px;
}
.report-rendered :deep(th),
.report-rendered :deep(td) {
  border: 1px solid var(--border-subtle);
  padding: 8px 12px;
  text-align: left;
}
.report-rendered :deep(th) {
  background: var(--bg-canvas);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: var(--text-muted);
}
.report-rendered :deep(blockquote) {
  border-left: 3px solid var(--border-default);
  margin: 12px 0;
  padding: 8px 16px;
  color: var(--text-muted);
  font-style: italic;
}
.report-rendered :deep(code) {
  background: var(--bg-overlay);
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 12px;
  font-family: var(--font-mono);
}
.report-rendered :deep(pre) {
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  padding: 14px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 12px 0;
}
.report-rendered :deep(pre code) {
  background: none;
  padding: 0;
}
.report-rendered :deep(strong) {
  font-weight: 600;
}
</style>
