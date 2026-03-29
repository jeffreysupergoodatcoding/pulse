<template>
  <div class="gv-root">

    <!-- Left: graph panel -->
    <div class="gv-left">
      <div class="gv-graph-header">
        <span class="gv-graph-title">Graph Relationship Visualization</span>
        <div class="gv-graph-actions">
          <button class="ctrl-btn" @click="loadSentiment" title="Refresh">↺ Refresh</button>
        </div>
      </div>
      <div class="gv-graph-body">
        <GraphPanel :entity-id="entityId" />
      </div>
    </div>

    <!-- Right: info panels -->
    <div class="gv-right">

      <!-- Sentiment card -->
      <div class="gv-panel">
        <div class="gv-panel-label">Sentiment Score</div>
        <div v-if="sentiment.current_score != null" class="gv-sentiment">
          <span class="badge" :class="sentimentBadge(sentiment.current_score)" style="font-size:18px;padding:6px 14px">
            {{ formatScore(sentiment.current_score) }}
          </span>
          <span class="gv-sentiment-label">{{ sentimentLabel(sentiment.current_score) }}</span>
        </div>
        <div v-else class="gv-empty-text">No sentiment data yet.</div>
      </div>

      <!-- Graph search -->
      <div class="gv-panel gv-panel-flex">
        <div class="gv-panel-label">Knowledge Search</div>
        <div class="gv-search-row">
          <input
            v-model="query"
            placeholder="Search graph…"
            @keydown.enter="search"
            aria-label="Search graph"
          />
          <button class="btn btn-primary btn-sm" :disabled="searching" @click="search">
            {{ searching ? '…' : 'Search' }}
          </button>
        </div>
        <div v-if="results.length" class="gv-results">
          <div v-for="(r, i) in results" :key="i" class="gv-result-item">
            <span class="score-pill">{{ r.score?.toFixed(2) }}</span>
            <span class="gv-result-text">{{ truncate(r.content, 140) }}</span>
          </div>
        </div>
        <div v-else-if="searched" class="gv-empty-text">No results found.</div>
      </div>

      <!-- Ontology topics -->
      <div class="gv-panel gv-panel-flex">
        <div class="gv-panel-label">Key Topics</div>
        <div v-if="ontology.entity_types?.length || ontology.relation_types?.length" class="gv-topics">
          <span
            v-for="topic in [...(ontology.entity_types || []), ...(ontology.relation_types || [])].slice(0, 20)"
            :key="topic"
            class="gv-topic-chip"
          >#{{ topic }}</span>
        </div>
        <div v-else class="gv-empty-text">Entity types &amp; relations appear after graph is built.</div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { graph as graphApi } from '../api/graph.js'
const GraphPanel = defineAsyncComponent(() => import('../components/GraphPanel.vue'))

const route = useRoute()
const entityId = route.params.id

const sentiment = ref({})
const query = ref('')
const results = ref([])
const searched = ref(false)
const searching = ref(false)
const ontology = ref({})

async function loadSentiment() {
  try {
    const r = await graphApi.getSentiment(entityId)
    sentiment.value = r.data
  } catch { /* ignore */ }
}

async function loadOntology() {
  try {
    const r = await graphApi.getOntology(entityId)
    ontology.value = r.data
  } catch { /* ignore */ }
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    const r = await graphApi.search(entityId, { query: query.value, k: 8 })
    results.value = r.data.episodes || r.data.results || []
    searched.value = true
  } finally {
    searching.value = false
  }
}

function sentimentBadge(s) { return s > 0.1 ? 'badge-positive' : s < -0.1 ? 'badge-negative' : 'badge-neutral' }
function formatScore(s) { return (s >= 0 ? '+' : '') + Number(s).toFixed(2) }
function sentimentLabel(s) {
  if (s > 0.5) return 'Highly Positive'
  if (s > 0.1) return 'Positive'
  if (s < -0.5) return 'Highly Negative'
  if (s < -0.1) return 'Negative'
  return 'Neutral'
}
function truncate(s, n) { return s?.length > n ? s.slice(0, n) + '…' : s }

onMounted(() => {
  loadSentiment()
  loadOntology()
})
</script>

<style scoped>
.gv-root {
  display: grid;
  grid-template-columns: 60fr 40fr;
  height: 100%;
  overflow: hidden;
}

/* Left graph area */
.gv-left {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-subtle);
  overflow: hidden;
}

.gv-graph-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  flex-shrink: 0;
}
.gv-graph-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.gv-graph-actions { display: flex; gap: 6px; }
.ctrl-btn {
  padding: 4px 10px;
  font-size: 11px;
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-muted);
  transition: background var(--transition-fast), color var(--transition-fast);
}
.ctrl-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

.gv-graph-body {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* Right info area */
.gv-right {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-canvas);
  gap: 0;
}

.gv-panel {
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.gv-panel-flex {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
.gv-panel-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-faint);
  margin-bottom: 12px;
}

/* Sentiment */
.gv-sentiment {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gv-sentiment-label {
  font-size: 12px;
  color: var(--text-muted);
}

/* Search */
.gv-search-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.gv-search-row input { flex: 1; }

.gv-results {
  overflow-y: auto;
  max-height: 260px;
}
.gv-result-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.gv-result-item:last-child { border-bottom: none; }
.score-pill {
  padding: 2px 6px;
  background: var(--bg-overlay);
  border-radius: var(--radius-sm);
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-family: var(--font-mono);
}
.gv-result-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Topics */
.gv-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gv-topic-chip {
  font-size: 12px;
  padding: 4px 10px;
  background: var(--bg-overlay);
  color: var(--text-muted);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-subtle);
  font-weight: 500;
  transition: background var(--transition-fast), color var(--transition-fast);
  cursor: default;
}
.gv-topic-chip:hover {
  background: var(--accent-light);
  color: var(--accent);
  border-color: var(--accent);
}

.gv-empty-text {
  font-size: 12px;
  color: var(--text-faint);
}
</style>
