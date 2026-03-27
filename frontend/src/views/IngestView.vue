<template>
  <div>
    <div class="section-title">Data Ingestion — {{ entityId }}</div>

    <div class="grid-2" style="max-width:900px">
      <div class="card">
        <div style="font-size:14px;font-weight:600;margin-bottom:12px">Sources</div>

        <div class="source-block">
          <label class="platform-label">
            <input type="checkbox" v-model="enabled.reddit" /> Reddit
          </label>
          <input
            v-if="enabled.reddit"
            v-model="sources.reddit"
            placeholder="subreddits, comma-separated (e.g. Nike, Sneakers)"
            class="source-input"
          />
        </div>

        <div class="source-block">
          <label class="platform-label">
            <input type="checkbox" v-model="enabled.twitter" /> Twitter / X
          </label>
          <input
            v-if="enabled.twitter"
            v-model="sources.twitter"
            placeholder="search queries, comma-separated (e.g. Nike, #Nike)"
            class="source-input"
          />
        </div>

        <div class="source-block">
          <label class="platform-label">
            <input type="checkbox" v-model="enabled.youtube" /> YouTube
          </label>
          <input
            v-if="enabled.youtube"
            v-model="sources.youtube"
            placeholder="video IDs, comma-separated"
            class="source-input"
          />
        </div>

        <div class="source-block">
          <label class="platform-label">
            <input type="checkbox" v-model="enabled.rss" /> RSS
          </label>
          <input
            v-if="enabled.rss"
            v-model="sources.rss"
            placeholder="feed URLs, comma-separated"
            class="source-input"
          />
        </div>

        <div class="mt-3">
          <label>Max posts per source</label>
          <input v-model.number="limit" type="number" min="5" max="500" style="width:100px" />
        </div>

        <button class="btn btn-primary mt-4" :disabled="pulling || !hasAnySources" @click="pull">
          {{ pulling ? 'Pulling…' : 'Pull Now' }}
        </button>

        <div v-if="taskId" class="mt-3">
          <div class="text-muted" style="font-size:12px;margin-bottom:6px">Task: {{ taskId }}</div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: (taskStatus.progress || 0) + '%' }" />
          </div>
          <div class="text-muted mt-2">{{ taskStatus.status }}</div>
          <div v-if="taskStatus.records_new !== undefined" class="text-muted" style="font-size:12px">
            {{ taskStatus.records_new }} new / {{ taskStatus.records_pulled }} pulled
          </div>
          <div v-if="taskStatus.errors?.length" class="error-list mt-2">
            <div v-for="(e, i) in taskStatus.errors" :key="i" style="font-size:11px;color:var(--negative)">{{ e }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div style="font-size:14px;font-weight:600;margin-bottom:12px">Preview</div>
        <button class="btn btn-secondary btn-sm" @click="loadPreview">Refresh Preview</button>
        <div v-if="preview.length" class="preview-list mt-3">
          <div v-for="(p, i) in preview.slice(0, 6)" :key="i" class="preview-item">
            <span class="badge badge-neutral" style="margin-right:6px">{{ p.platform }}</span>
            <span style="font-size:12px;color:var(--text-secondary)">{{ truncate(p.content, 120) }}</span>
          </div>
        </div>
        <div v-else class="text-muted mt-3" style="font-size:12px">No ingested posts yet.</div>
      </div>
    </div>

    <!-- Build graph CTA -->
    <div class="card mt-4" style="max-width:400px">
      <div style="font-size:14px;font-weight:600;margin-bottom:8px">Build Knowledge Graph</div>
      <div class="text-muted" style="font-size:12px;margin-bottom:12px">
        Run GraphRAG on ingested posts to populate the Zep knowledge graph.
      </div>
      <button class="btn btn-primary" :disabled="building" @click="buildGraph">
        {{ building ? 'Building…' : 'Build Graph' }}
      </button>
      <div v-if="buildResult" class="mt-2 text-muted" style="font-size:12px">
        ✓ {{ buildResult.nodes_added }} nodes, {{ buildResult.edges_added }} edges,
        {{ buildResult.episodes_added }} episodes
      </div>
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
  const platformMap = {
    reddit: 'reddit',
    twitter: 'twitter',
    youtube: 'youtube',
    rss: 'rss',
  }
  for (const [key, platform] of Object.entries(platformMap)) {
    if (!enabled.value[key]) continue
    const raw = sources.value[key] || ''
    const ids = raw.split(',').map(s => s.trim()).filter(Boolean)
    if (ids.length) result.push({ platform, ids })
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
    // Persist source config back to entity before pulling
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
  // Pre-populate source inputs from entity's saved source_config
  try {
    const r = await graphApi.getEntity(entityId)
    const cfg = r.data.source_config || {}
    if (cfg.reddit?.subreddits?.length) {
      sources.value.reddit = cfg.reddit.subreddits.join(', ')
      enabled.value.reddit = true
    }
    if (cfg.twitter?.queries?.length) {
      sources.value.twitter = cfg.twitter.queries.join(', ')
      enabled.value.twitter = true
    }
    if (cfg.youtube?.video_ids?.length) {
      sources.value.youtube = cfg.youtube.video_ids.join(', ')
      enabled.value.youtube = true
    }
    if (cfg.rss?.feed_urls?.length) {
      sources.value.rss = cfg.rss.feed_urls.join(', ')
      enabled.value.rss = true
    }
  } catch { /* entity fetch failed, start with empty inputs */ }

  loadPreview()
})
</script>

<style scoped>
.source-block { margin-bottom: 14px; }
.platform-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-primary); cursor: pointer; margin-bottom: 6px; font-weight: 600; }
.source-input { width: 100%; box-sizing: border-box; font-size: 12px; }
.progress-bar { height: 6px; background: var(--bg-overlay); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width .3s; }
.preview-list { display: flex; flex-direction: column; gap: 8px; }
.preview-item { padding: 6px 10px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); }
.error-list { background: var(--negative-bg); border-radius: var(--radius-sm); padding: 6px 8px; }
</style>
