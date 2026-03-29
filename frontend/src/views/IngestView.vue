<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">Data Ingestion</h1>
        <p class="view-subtitle">Pull content from social platforms into the knowledge graph</p>
      </div>
    </div>

    <!-- Slim progress bar (shown during pull) -->
    <div v-if="taskId" class="ingest-progress-wrap">
      <div class="ingest-progress-bar" :style="{ width: (taskStatus.progress || 5) + '%' }" />
    </div>
    <div v-if="taskId" class="ingest-task-status">
      <span class="task-id">{{ taskId.slice(0, 8) }}</span>
      <span class="task-sep">·</span>
      <span class="task-stat" :class="taskStatus.status">{{ taskStatus.status }}</span>
      <span v-if="taskStatus.records_new !== undefined" class="task-sep">·</span>
      <span v-if="taskStatus.records_new !== undefined" class="task-counts">
        {{ taskStatus.records_new }} new · {{ taskStatus.records_pulled }} pulled
      </span>
    </div>

    <div class="ingest-grid">
      <!-- Sources card -->
      <div class="card">
        <div class="card-label">Sources</div>

        <div class="platform-list">
          <div class="platform-row" v-for="p in platforms" :key="p.key">
            <div class="platform-header">
              <button
                class="platform-toggle"
                :class="{ active: enabled[p.key] }"
                @click="enabled[p.key] = !enabled[p.key]"
              >
                <span class="toggle-dot" />
                {{ p.name }}
              </button>
            </div>
            <input
              v-if="enabled[p.key]"
              v-model="sources[p.key]"
              :placeholder="p.placeholder"
              class="source-input"
            />
          </div>
        </div>

        <div class="limit-row">
          <label class="limit-label">Max per source</label>
          <input v-model.number="limit" type="number" min="5" max="500" class="limit-input" />
        </div>

        <div class="pull-row">
          <button
            class="btn btn-primary pull-btn"
            :disabled="pulling || !hasAnySources"
            @click="pull"
          >
            {{ pulling ? 'Pulling…' : 'Pull Now' }}
          </button>
        </div>

        <div v-if="taskStatus.errors?.length" class="error-list">
          <div v-for="(e, i) in taskStatus.errors" :key="i" class="error-item">{{ e }}</div>
        </div>
      </div>

      <!-- Preview card -->
      <div class="card">
        <div class="card-label-row">
          <div class="card-label">Preview</div>
          <button class="btn btn-secondary btn-sm" @click="loadPreview">Refresh</button>
        </div>
        <div v-if="preview.length" class="preview-list">
          <div v-for="(p, i) in preview.slice(0, 6)" :key="i" class="preview-item">
            <span class="preview-badge">{{ p.platform }}</span>
            <span class="preview-text">{{ truncate(p.content, 120) }}</span>
          </div>
        </div>
        <div v-else class="preview-empty">No ingested posts yet.</div>
      </div>
    </div>

    <!-- Build graph CTA banner -->
    <div class="build-graph-banner">
      <div class="build-graph-info">
        <span class="build-graph-icon">◎</span>
        <div>
          <div class="build-graph-title">Build Knowledge Graph</div>
          <div class="build-graph-sub">Run GraphRAG on ingested posts to populate the knowledge graph</div>
          <div v-if="buildResult" class="build-graph-result">
            ✓ {{ buildResult.nodes_added }} nodes · {{ buildResult.edges_added }} edges · {{ buildResult.episodes_added }} episodes
          </div>
        </div>
      </div>
      <button class="btn btn-primary" :disabled="building" @click="buildGraph">
        {{ building ? 'Building…' : 'Build Graph →' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ingestion as ingestionApi } from '../api/ingestion.js'
import { graph as graphApi } from '../api/graph.js'

const route = useRoute()
const entityId = route.params.id

const platforms = [
  { key: 'reddit',  name: 'Reddit',     placeholder: 'subreddits, comma-separated (e.g. Nike, Sneakers)' },
  { key: 'twitter', name: 'Twitter / X', placeholder: 'search queries, comma-separated (e.g. Nike, #Nike)' },
  { key: 'youtube', name: 'YouTube',    placeholder: 'video IDs, comma-separated' },
  { key: 'rss',     name: 'RSS',        placeholder: 'feed URLs, comma-separated' },
]

const enabled = ref({ reddit: true, twitter: false, youtube: false, rss: false })
const sources = ref({ reddit: '', twitter: '', youtube: '', rss: '' })
const limit = ref(200)
const pulling = ref(false)
const taskId = ref('')
const taskStatus = ref({})
const preview = ref([])
const building = ref(false)
const buildResult = ref(null)
let pollTimer = null

const hasAnySources = computed(() =>
  Object.entries(enabled.value).some(([p, on]) => on && sources.value[p]?.trim())
)

function buildSourcesPayload() {
  const result = []
  for (const { key } of platforms) {
    if (!enabled.value[key]) continue
    const ids = (sources.value[key] || '').split(',').map(s => s.trim()).filter(Boolean)
    if (ids.length) result.push({ platform: key, ids })
  }
  return result
}

function buildSourceConfig() {
  const toList = (str) => str.split(',').map(s => s.trim()).filter(Boolean)
  return {
    reddit:  { subreddits: enabled.value.reddit  ? toList(sources.value.reddit)  : [] },
    twitter: { queries:    enabled.value.twitter ? toList(sources.value.twitter) : [] },
    youtube: { video_ids:  enabled.value.youtube ? toList(sources.value.youtube) : [], channel_ids: [] },
    rss:     { feed_urls:  enabled.value.rss     ? toList(sources.value.rss)     : [] },
  }
}

async function pull() {
  pulling.value = true
  taskId.value = ''
  taskStatus.value = {}
  try {
    await graphApi.updateEntity(entityId, { source_config: buildSourceConfig() })
    const r = await ingestionApi.pull({
      entity_id: entityId,
      sources: buildSourcesPayload(),
      limit: limit.value,
    })
    taskId.value = r.data.task_id
    pollTask()
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    pulling.value = false
  }
}

function pollTask() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!taskId.value) return
    const r = await ingestionApi.getStatus(taskId.value)
    taskStatus.value = r.data
    if (['completed', 'error'].includes(r.data.status)) {
      clearInterval(pollTimer)
      if (r.data.status === 'completed') loadPreview()
    }
  }, 1500)
}

async function loadPreview() {
  try {
    const r = await ingestionApi.preview(entityId)
    preview.value = r.data.records || r.data.posts || r.data || []
  } catch { /* ignore */ }
}

async function buildGraph() {
  building.value = true
  buildResult.value = null
  try {
    const r = await graphApi.build({ entity_id: entityId })
    buildResult.value = r.data
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    building.value = false
  }
}

function truncate(s, n) { return s?.length > n ? s.slice(0, n) + '…' : s }

onMounted(async () => {
  try {
    const r = await graphApi.getEntity(entityId)
    const cfg = r.data.source_config || {}
    if (cfg.reddit?.subreddits?.length)  { sources.value.reddit  = cfg.reddit.subreddits.join(', ');  enabled.value.reddit  = true }
    if (cfg.twitter?.queries?.length)    { sources.value.twitter = cfg.twitter.queries.join(', ');    enabled.value.twitter = true }
    if (cfg.youtube?.video_ids?.length)  { sources.value.youtube = cfg.youtube.video_ids.join(', ');  enabled.value.youtube = true }
    if (cfg.rss?.feed_urls?.length)      { sources.value.rss     = cfg.rss.feed_urls.join(', ');      enabled.value.rss     = true }
  } catch { /* ignore */ }
  loadPreview()
})
</script>

<style scoped>
.ingest-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  max-width: 900px;
  margin-bottom: 16px;
}

/* Card label */
.card-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.1px;
  color: var(--text-faint);
  margin-bottom: 18px;
  font-family: var(--font-sans);
}

.card-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.card-label-row .card-label { margin-bottom: 0; }

/* Platform list */
.platform-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.platform-row { display: flex; flex-direction: column; gap: 8px; }

.platform-header { display: flex; align-items: center; }

.platform-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
  letter-spacing: -0.1px;
}
.platform-toggle:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}
.platform-toggle.active {
  border-color: var(--text-primary);
  background: var(--text-primary);
  color: #FFFFFF;
}

.toggle-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-default);
  flex-shrink: 0;
  transition: background var(--transition-fast);
}
.platform-toggle.active .toggle-dot { background: #FFFFFF; }

.source-input {
  width: 100%;
  box-sizing: border-box;
  font-size: 12px;
}

/* Limit + Pull row */
.limit-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}
.limit-label {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  font-weight: 500;
}
.limit-input {
  width: 80px;
  font-size: 13px;
  padding: 5px 8px;
}

.pull-row {
  display: flex;
  align-items: center;
}
.pull-btn {
  width: auto;
  padding: 8px 20px;
}

.error-list { margin-top: 12px; }
.error-item {
  font-size: 11px;
  color: var(--negative);
  padding: 4px 0;
  border-bottom: 1px solid var(--border-subtle);
}

/* Preview */
.preview-list { display: flex; flex-direction: column; gap: 8px; }
.preview-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: var(--bg-canvas);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}
.preview-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: var(--bg-overlay);
  color: var(--text-muted);
  border: 1px solid var(--border-subtle);
  font-family: var(--font-mono);
  margin-top: 1px;
}
.preview-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.preview-empty {
  font-size: 12px;
  color: var(--text-faint);
  padding: 16px 0;
}

/* Slim progress */
.ingest-progress-wrap {
  height: 3px;
  background: var(--bg-overlay);
  margin: -24px -24px 0;
  overflow: hidden;
}
.ingest-progress-bar {
  height: 100%;
  background: var(--text-primary);
  transition: width 0.3s;
}
.ingest-task-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 6px 0 12px;
  font-family: var(--font-mono);
  color: var(--text-faint);
}
.task-id { color: var(--text-faint); }
.task-sep { color: var(--border-default); }
.task-stat { font-weight: 600; color: var(--text-muted); }
.task-stat.completed { color: var(--positive); }
.task-stat.error     { color: var(--negative); }
.task-counts { color: var(--text-faint); }

/* Build graph banner */
.build-graph-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--text-primary);
  border-radius: var(--radius-lg);
  flex-wrap: wrap;
  max-width: 900px;
  box-shadow: var(--shadow-sm);
}
.build-graph-info {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.build-graph-icon {
  font-size: 22px;
  color: var(--text-primary);
  line-height: 1;
  margin-top: 2px;
  opacity: 0.7;
}
.build-graph-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 3px;
  letter-spacing: -0.2px;
}
.build-graph-sub {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
.build-graph-result {
  font-size: 12px;
  color: var(--positive);
  margin-top: 6px;
  font-weight: 600;
}
</style>
