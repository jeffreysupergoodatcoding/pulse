<template>
  <div>
    <div class="section-title">Knowledge Graph — {{ entityId }}</div>

    <GraphPanel :entity-id="entityId" />

    <div class="grid-2 mt-4">
      <div class="card">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px">Sentiment</div>
        <div v-if="sentiment.current_score != null">
          <span class="badge" :class="sentimentBadge(sentiment.current_score)" style="font-size:18px;padding:4px 12px">
            {{ formatScore(sentiment.current_score) }}
          </span>
        </div>
        <div v-else class="text-muted" style="font-size:13px">No sentiment data yet.</div>
      </div>

      <div class="card">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px">Graph Search</div>
        <div class="flex gap-2">
          <input v-model="query" placeholder="Search graph…" @keydown.enter="search" />
          <button class="btn btn-primary btn-sm" :disabled="searching" @click="search">Search</button>
        </div>
        <div v-if="results.length" class="mt-3">
          <div v-for="(r, i) in results" :key="i" class="search-result">
            <span class="score-pill">{{ r.score?.toFixed(2) }}</span>
            <span style="font-size:12px;color:var(--text-secondary)">{{ truncate(r.content, 120) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { graph as graphApi } from '../api/graph.js'
import { defineAsyncComponent } from 'vue'
const GraphPanel = defineAsyncComponent(() => import('../components/GraphPanel.vue'))

const route = useRoute()
const entityId = route.params.id
const sentiment = ref({})
const query = ref('')
const results = ref([])
const searching = ref(false)

async function loadSentiment() {
  try {
    const r = await graphApi.getSentiment(entityId)
    sentiment.value = r.data
  } catch { /* ignore */ }
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const r = await graphApi.search(entityId, { query: query.value, k: 8 })
    results.value = r.data.results || r.data || []
  } finally {
    searching.value = false
  }
}

function sentimentBadge(s) { return s > 0.1 ? 'badge-positive' : s < -0.1 ? 'badge-negative' : 'badge-neutral' }
function formatScore(s) { return (s >= 0 ? '+' : '') + Number(s).toFixed(2) }
function truncate(s, n) { return s?.length > n ? s.slice(0, n) + '…' : s }

onMounted(loadSentiment)
</script>

<style scoped>
.search-result { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border-subtle); }
.score-pill { padding: 1px 6px; background: var(--bg-overlay); border-radius: var(--radius-sm); font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
</style>
