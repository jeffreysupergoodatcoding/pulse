<template>
  <div>
    <div class="flex" style="align-items:center;justify-content:space-between;margin-bottom:20px">
      <div class="section-title" style="margin-bottom:0">Report — {{ reportId }}</div>
      <div class="flex gap-2">
        <span class="badge" :class="statusBadge">{{ reportState.status || 'loading' }}</span>
        <div v-if="reportState.status === 'running'" class="text-muted" style="font-size:12px;align-self:center">
          {{ reportState.sections_done }}/{{ reportState.total_sections }} sections
        </div>
        <router-link :to="`/entity/${entityId}/interact/${reportId}`" class="btn btn-secondary btn-sm">
          Chat →
        </router-link>
      </div>
    </div>

    <!-- Progress bar while generating -->
    <div v-if="reportState.status === 'running'" class="progress-wrap card mb-4">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
      <div class="text-muted mt-2" style="font-size:12px">Generating report with ReACT agent…</div>
    </div>

    <div v-if="markdown" class="grid-layout">
      <!-- Main report -->
      <div class="card report-body" v-html="renderedMarkdown" />

      <!-- Side panel: sentiment + drilldown -->
      <div class="side-panel">
        <div class="card mb-3">
          <div style="font-size:13px;font-weight:600;margin-bottom:10px">Sentiment Trajectory</div>
          <SentimentChart :sentiment-by-round="sentimentData.sentiment_by_round || []" />
        </div>

        <div class="card mb-3">
          <div style="font-size:13px;font-weight:600;margin-bottom:10px">MiroSignal</div>
          <div v-if="signal.signal_type" class="signal-box">
            <div class="flex gap-2" style="align-items:center;margin-bottom:8px">
              <span class="badge" :class="`badge-${signal.signal_type === 'positive' ? 'positive' : signal.signal_type === 'negative' ? 'negative' : 'neutral'}`">
                {{ signal.signal_type }}
              </span>
              <span class="text-muted" style="font-size:12px">{{ (signal.confidence * 100).toFixed(0) }}% confidence</span>
            </div>
            <div style="font-size:12px;margin-bottom:6px">{{ signal.summary }}</div>
            <div v-if="signal.top_risk" class="signal-item neg">⚠ {{ signal.top_risk }}</div>
            <div v-if="signal.top_opportunity" class="signal-item pos">✓ {{ signal.top_opportunity }}</div>
          </div>
          <button v-else class="btn btn-secondary btn-sm" :disabled="loadingSignal" @click="loadSignal">
            {{ loadingSignal ? 'Generating…' : 'Generate Signal' }}
          </button>
        </div>

        <div class="card">
          <div style="font-size:13px;font-weight:600;margin-bottom:10px">Drilldown</div>
          <div>
            <label>Filter by archetype</label>
            <input v-model="drillFilter" placeholder="sneakerheads…" />
          </div>
          <button class="btn btn-secondary btn-sm mt-2" @click="runDrilldown">Filter</button>
          <div v-if="drillResult.narratives?.length" class="mt-3">
            <div v-for="(n, i) in drillResult.narratives.slice(0, 3)" :key="i" class="narrative-item">
              <span class="text-muted" style="font-size:11px">{{ n.sentiment_score?.toFixed(2) }}</span>
              {{ n.text }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="reportState.status !== 'running' && reportState.status !== 'loading'" class="text-muted">
      Report content not available yet.
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { report as reportApi } from '../api/report.js'
import { simulation as simApi } from '../api/simulation.js'
import SentimentChart from '../components/SentimentChart.vue'

const route = useRoute()
const entityId = route.params.id
const reportId = route.params.rid
const markdown = ref('')
const reportState = ref({ status: 'loading', sections_done: 0, total_sections: 8 })
const sentimentData = ref({})
const signal = ref({})
const loadingSignal = ref(false)
const drillFilter = ref('')
const drillResult = ref({})
let pollTimer = null

const renderedMarkdown = computed(() => marked.parse(markdown.value || ''))
const progressPct = computed(() => {
  const s = reportState.value
  return Math.round((s.sections_done / (s.total_sections || 8)) * 100)
})
const statusBadge = computed(() => ({
  'badge-positive': reportState.value.status === 'completed',
  'badge-negative': reportState.value.status === 'error',
  'badge-neutral': !['completed', 'error'].includes(reportState.value.status),
}))

async function poll() {
  const r = await reportApi.getStatus(reportId)
  reportState.value = r.data
  if (r.data.status === 'completed') {
    clearInterval(pollTimer)
    loadContent()
    loadSentiment()
  }
}

async function loadContent() {
  const r = await reportApi.getContent(reportId)
  markdown.value = r.data.markdown || ''
}

async function loadSentiment() {
  // Get sim_id from localStorage (saved in SimulationView)
  const simId = localStorage.getItem(`sim_${entityId}`)
  if (!simId) return
  try {
    const r = await simApi.getSentiment(simId)
    sentimentData.value = r.data
  } catch { /* ignore */ }
}

async function loadSignal() {
  loadingSignal.value = true
  try {
    const r = await reportApi.signal(reportId)
    signal.value = r.data.miro_signal || {}
  } finally {
    loadingSignal.value = false
  }
}

async function runDrilldown() {
  const r = await reportApi.drilldown(reportId, {
    entity_id: entityId,
    persona_filter: drillFilter.value || undefined,
  })
  drillResult.value = r.data
}

onMounted(() => {
  poll()
  pollTimer = setInterval(poll, 3000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.grid-layout { display: grid; grid-template-columns: 1fr 340px; gap: 20px; align-items: start; }
.side-panel { display: flex; flex-direction: column; }
.mb-3 { margin-bottom: 12px; }
.mb-4 { margin-bottom: 16px; }
.progress-wrap { }
.progress-bar { height: 6px; background: #1e2433; border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: #7c3aed; transition: width .5s; }

.report-body :deep(h1) { font-size: 22px; font-weight: 700; margin: 0 0 16px; color: #f1f5f9; }
.report-body :deep(h2) { font-size: 17px; font-weight: 600; margin: 24px 0 10px; color: #e2e8f0; border-bottom: 1px solid #2d3748; padding-bottom: 6px; }
.report-body :deep(h3) { font-size: 14px; font-weight: 600; margin: 16px 0 8px; color: #cbd5e1; }
.report-body :deep(p)  { font-size: 13px; line-height: 1.7; color: #94a3b8; margin: 0 0 12px; }
.report-body :deep(ul), .report-body :deep(ol) { padding-left: 20px; color: #94a3b8; font-size: 13px; margin: 0 0 12px; }
.report-body :deep(li) { margin-bottom: 4px; line-height: 1.6; }
.report-body :deep(strong) { color: #e2e8f0; }
.report-body :deep(hr) { border: none; border-top: 1px solid #2d3748; margin: 20px 0; }

.signal-box { }
.signal-item { font-size: 12px; padding: 4px 8px; border-radius: 4px; margin-top: 4px; }
.signal-item.pos { background: #14532d33; color: #4ade80; }
.signal-item.neg { background: #450a0a33; color: #f87171; }
.narrative-item { font-size: 12px; color: #94a3b8; padding: 4px 0; border-bottom: 1px solid #1e2433; }
</style>
