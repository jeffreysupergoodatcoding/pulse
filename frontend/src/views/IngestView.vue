<template>
  <div>
    <div class="view-header">
      <div>
        <h1 class="view-title">Data Ingestion</h1>
        <p class="view-subtitle">Pull content from social platforms into the knowledge graph</p>
      </div>
    </div>

    <!-- Mode toggle -->
    <div class="ingest-mode-toggle">
      <button
        class="mode-btn"
        :class="{ active: mode === 'auto' }"
        @click="mode = 'auto'"
      >Auto</button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'manual' }"
        @click="mode = 'manual'"
      >Manual</button>
      <button
        class="mode-btn"
        :class="{ active: mode === 'upload' }"
        @click="mode = 'upload'"
      >Upload</button>
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

    <!-- ── AUTO MODE ──────────────────────────────── -->
    <div v-if="mode === 'auto'" class="ingest-grid">
      <div class="card">
        <div class="card-label">What to search for</div>
        <p class="auto-desc">
          Automatically searches Reddit, Hacker News, YouTube, and Google News
          using the entity's name and keywords. Add extra search terms below to
          refine what gets pulled.
        </p>

        <div class="auto-field">
          <label>Extra search terms <span class="auto-hint">— comma-separated, optional</span></label>
          <input
            v-model="autoExtraTerms"
            placeholder="e.g. controversy, collaboration, earnings report"
          />
        </div>

        <div class="limit-row">
          <label class="limit-label">Max per source</label>
          <input v-model.number="limit" type="number" min="5" max="500" class="limit-input" />
        </div>

        <div class="pull-row">
          <button
            class="btn btn-primary pull-btn"
            :disabled="pulling || autoPulling"
            @click="autoPull"
          >
            {{ autoPulling ? 'Ingesting…' : 'Auto-Ingest' }}
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
          <div v-for="(p, i) in preview.slice(0, 10)" :key="i" class="preview-item">
            <span class="preview-badge">{{ p.platform }}</span>
            <span class="preview-text">{{ truncate(p.content, 120) }}</span>
          </div>
        </div>
        <div v-else class="preview-empty">No ingested posts yet.</div>
      </div>
    </div>

    <!-- ── MANUAL MODE ────────────────────────────── -->
    <div v-else class="ingest-grid">
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
          <div v-for="(p, i) in preview.slice(0, 10)" :key="i" class="preview-item">
            <span class="preview-badge">{{ p.platform }}</span>
            <span class="preview-text">{{ truncate(p.content, 120) }}</span>
          </div>
        </div>
        <div v-else class="preview-empty">No ingested posts yet.</div>
      </div>
    </div>

    <!-- ── UPLOAD MODE ────────────────────────────── -->
    <div v-if="mode === 'upload'" class="ingest-grid">
      <div class="card">
        <div class="card-label">Upload Data</div>
        <p class="auto-desc">
          Bring your own data — drop a <strong>JSONL</strong> or <strong>CSV</strong> file
          conforming to the PostRecord schema. Once uploaded, the data is indistinguishable
          from API-ingested data downstream (graph, personas, simulation, audience discovery).
        </p>

        <p class="auto-desc">
          <strong>Required fields per row:</strong> <code>id</code>, <code>content</code>, <code>created_at</code>.
          Recommended: <code>platform</code>, <code>author_id</code> (will be SHA-256 anonymized),
          <code>engagement</code> object with likes/shares/replies/views.
        </p>

        <div class="upload-dropzone"
             :class="{ active: uploadDragOver }"
             @dragover.prevent="uploadDragOver = true"
             @dragleave.prevent="uploadDragOver = false"
             @drop.prevent="onUploadDrop">
          <input ref="uploadInput" type="file" accept=".jsonl,.ndjson,.csv" @change="onUploadFileChosen" style="display:none" />
          <div v-if="!uploadFile" class="upload-placeholder">
            <div class="upload-icon">⬆</div>
            <div class="upload-text">
              <strong>Drop file here</strong> or
              <button class="link-btn" @click="$refs.uploadInput.click()">browse</button>
            </div>
            <div class="upload-hint">Accepts .jsonl, .ndjson, .csv (up to ~100MB)</div>
          </div>
          <div v-else class="upload-selected">
            <div class="upload-filename">{{ uploadFile.name }}</div>
            <div class="upload-meta">{{ (uploadFile.size / 1024).toFixed(1) }} KB · {{ uploadFile.type || 'auto-detected' }}</div>
            <button class="link-btn" @click="uploadFile = null; uploadResult = null">change file</button>
          </div>
        </div>

        <div class="auto-field" v-if="uploadFile">
          <label>Default platform tag <span class="auto-hint">— used when records don't include a platform field</span></label>
          <input v-model="uploadDefaultPlatform" placeholder="uploaded" />
        </div>

        <div class="pull-row">
          <button class="btn btn-primary pull-btn" :disabled="!uploadFile || uploading" @click="runUpload">
            {{ uploading ? 'Uploading…' : 'Upload' }}
          </button>
        </div>

        <div v-if="uploadResult" class="upload-result">
          <div class="upload-result-line"><strong>Records added:</strong> {{ uploadResult.records_added }}</div>
          <div class="upload-result-line"><strong>Records skipped:</strong> {{ uploadResult.records_skipped }}</div>
          <div v-if="uploadResult.errors?.length" class="upload-errors">
            <div class="upload-errors-title">First {{ Math.min(uploadResult.errors.length, 5) }} errors:</div>
            <ul>
              <li v-for="(e, i) in uploadResult.errors.slice(0, 5)" :key="i">{{ e }}</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Preview card (shared) -->
      <div class="card">
        <div class="card-label-row">
          <div class="card-label">Preview</div>
          <button class="btn btn-secondary btn-sm" @click="loadPreview">Refresh</button>
        </div>
        <div v-if="preview.length" class="preview-list">
          <div v-for="(p, i) in preview.slice(0, 10)" :key="i" class="preview-item">
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
          <div v-if="buildStatus.status === 'running'" class="build-graph-progress-info">
            <div class="build-progress-wrap">
              <div class="build-progress-bar" :style="{ width: (buildStatus.progress || 5) + '%' }" />
            </div>
            <span class="build-progress-label">{{ buildProgressLabel }}</span>
          </div>
          <div v-if="buildStatus.status === 'completed' && buildResult" class="build-graph-result">
            {{ buildResult.nodes_added }} nodes · {{ buildResult.edges_added }} edges · {{ buildResult.episodes_added }} episodes
          </div>
          <div v-if="buildStatus.status === 'error'" class="build-graph-error">
            Build failed: {{ buildStatus.error || 'unknown error' }}
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

const mode = ref('auto')
const autoExtraTerms = ref('')

const platforms = [
  { key: 'reddit',     name: 'Reddit',        placeholder: 'subreddits, comma-separated (e.g. Nike, Sneakers)' },
  { key: 'twitter',    name: 'Twitter / X',   placeholder: 'search queries, comma-separated (e.g. Nike, #Nike)' },
  { key: 'youtube',    name: 'YouTube',       placeholder: 'video IDs, comma-separated' },
  { key: 'hackernews', name: 'Hacker News',   placeholder: 'search queries, comma-separated (e.g. OpenAI, LLM, startup)' },
  { key: 'amazon',     name: 'Amazon',        placeholder: 'ASINs, comma-separated (e.g. B08N5WRWNW)' },
  { key: 'appstore',   name: 'App Store',     placeholder: 'app-name/id123456, comma-separated (e.g. nike/id430865257)' },
  { key: 'gplay',      name: 'Google Play',   placeholder: 'package IDs, comma-separated (e.g. com.nike.omega)' },
  { key: 'rss',        name: 'RSS',           placeholder: 'feed URLs, comma-separated' },
]

const enabled = ref({ reddit: true, twitter: false, youtube: false, hackernews: false, amazon: false, appstore: false, gplay: false, rss: false })
const sources = ref({ reddit: '', twitter: '', youtube: '', hackernews: '', amazon: '', appstore: '', gplay: '', rss: '' })
const limit = ref(200)
const pulling = ref(false)
const autoPulling = ref(false)
const taskId = ref('')
const taskStatus = ref({})
const preview = ref([])
const building = ref(false)
const buildResult = ref(null)
const buildTaskId = ref('')
const buildStatus = ref({})
let pollTimer = null
let buildPollTimer = null

// Upload (BYO) state
const uploadFile = ref(null)
const uploadDragOver = ref(false)
const uploadDefaultPlatform = ref('uploaded')
const uploading = ref(false)
const uploadResult = ref(null)

const hasAnySources = computed(() =>
  Object.entries(enabled.value).some(([p, on]) => on && sources.value[p]?.trim())
)

const buildProgressLabel = computed(() => {
  const p = buildStatus.value.progress || 0
  if (p <= 10) return 'Reading ingested posts…'
  if (p <= 49) return 'Extracting ontology via LLM…'
  if (p <= 79) return 'Writing episodes to Zep…'
  if (p <= 99) return 'Storing nodes & edges…'
  return 'Done'
})

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
    reddit:     { subreddits: enabled.value.reddit     ? toList(sources.value.reddit)     : [] },
    twitter:    { queries:    enabled.value.twitter     ? toList(sources.value.twitter)    : [] },
    youtube:    { video_ids:  enabled.value.youtube     ? toList(sources.value.youtube)    : [], channel_ids: [] },
    hackernews: { queries:    enabled.value.hackernews  ? toList(sources.value.hackernews) : [] },
    amazon:     { asins:      enabled.value.amazon      ? toList(sources.value.amazon)     : [] },
    appstore:   { app_ids:    enabled.value.appstore    ? toList(sources.value.appstore)   : [] },
    gplay:      { app_ids:    enabled.value.gplay       ? toList(sources.value.gplay)      : [] },
    rss:        { feed_urls:  enabled.value.rss         ? toList(sources.value.rss)        : [] },
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

async function autoPull() {
  autoPulling.value = true
  taskId.value = ''
  taskStatus.value = {}
  try {
    const extra = autoExtraTerms.value.split(',').map(s => s.trim()).filter(Boolean)
    const r = await ingestionApi.autoPull({
      entity_id: entityId,
      limit: limit.value,
      extra_terms: extra.length ? extra : undefined,
    })
    taskId.value = r.data.task_id
    pollTask()
  } catch (e) {
    alert(e.response?.data?.error || e.message)
  } finally {
    autoPulling.value = false
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
    const r = await ingestionApi.preview(entityId, 20)
    preview.value = r.data.records || r.data.posts || r.data || []
  } catch { /* ignore */ }
}

function onUploadFileChosen(e) {
  const f = e.target.files?.[0]
  if (f) uploadFile.value = f
}
function onUploadDrop(e) {
  uploadDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) uploadFile.value = f
}

async function runUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  uploadResult.value = null
  try {
    const name = uploadFile.value.name.toLowerCase()
    const fileFormat = name.endsWith('.csv') ? 'csv' : 'jsonl'
    const r = await ingestionApi.upload(entityId, uploadFile.value, {
      fileFormat,
      defaultPlatform: uploadDefaultPlatform.value || 'uploaded',
    })
    uploadResult.value = r.data
    // Auto-refresh preview to show what got ingested
    loadPreview()
  } catch (e) {
    uploadResult.value = {
      records_added: 0, records_skipped: 0,
      errors: [e.response?.data?.error || e.message],
    }
  } finally {
    uploading.value = false
  }
}

async function buildGraph() {
  building.value = true
  buildResult.value = null
  buildStatus.value = { status: 'running', progress: 5 }
  try {
    const r = await graphApi.build({ entity_id: entityId })
    buildTaskId.value = r.data.task_id
    pollBuildTask()
  } catch (e) {
    building.value = false
    buildStatus.value = { status: 'error', error: e.response?.data?.error || e.message }
  }
}

function pollBuildTask() {
  clearInterval(buildPollTimer)
  buildPollTimer = setInterval(async () => {
    if (!buildTaskId.value) return
    try {
      const r = await graphApi.getBuildStatus(buildTaskId.value)
      buildStatus.value = r.data
      if (r.data.status === 'completed') {
        clearInterval(buildPollTimer)
        building.value = false
        buildResult.value = {
          nodes_added: r.data.nodes_added || 0,
          edges_added: r.data.edges_added || 0,
          episodes_added: r.data.episodes_added || 0,
        }
      } else if (r.data.status === 'error') {
        clearInterval(buildPollTimer)
        building.value = false
      }
    } catch {
      /* keep polling */
    }
  }, 2000)
}

function truncate(s, n) { return s?.length > n ? s.slice(0, n) + '…' : s }

onMounted(async () => {
  try {
    const r = await graphApi.getEntity(entityId)
    const cfg = r.data.source_config || {}
    if (cfg.reddit?.subreddits?.length)    { sources.value.reddit     = cfg.reddit.subreddits.join(', ');     enabled.value.reddit     = true }
    if (cfg.twitter?.queries?.length)      { sources.value.twitter    = cfg.twitter.queries.join(', ');      enabled.value.twitter    = true }
    if (cfg.youtube?.video_ids?.length)    { sources.value.youtube    = cfg.youtube.video_ids.join(', ');    enabled.value.youtube    = true }
    if (cfg.hackernews?.queries?.length)   { sources.value.hackernews = cfg.hackernews.queries.join(', ');   enabled.value.hackernews = true }
    if (cfg.amazon?.asins?.length)         { sources.value.amazon     = cfg.amazon.asins.join(', ');         enabled.value.amazon     = true }
    if (cfg.appstore?.app_ids?.length)     { sources.value.appstore   = cfg.appstore.app_ids.join(', ');     enabled.value.appstore   = true }
    if (cfg.gplay?.app_ids?.length)        { sources.value.gplay      = cfg.gplay.app_ids.join(', ');        enabled.value.gplay      = true }
    if (cfg.rss?.feed_urls?.length)        { sources.value.rss        = cfg.rss.feed_urls.join(', ');        enabled.value.rss        = true }
  } catch { /* ignore */ }
  loadPreview()
})
</script>

<style scoped>
/* Mode toggle */
.ingest-mode-toggle {
  display: inline-flex;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 20px;
}
.mode-btn {
  padding: 7px 20px;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  border: none;
  background: var(--bg-surface);
  color: var(--text-muted);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
  letter-spacing: -0.1px;
}
.mode-btn:not(:last-child) {
  border-right: 1px solid var(--border-default);
}
.mode-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.mode-btn.active {
  background: var(--text-primary);
  color: #FFFFFF;
}

/* Auto mode */
.auto-desc {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 0 0 18px;
}
.auto-field {
  margin-bottom: 16px;
}
.auto-field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
  display: block;
}
.auto-hint {
  font-weight: 400;
  color: var(--text-faint);
  font-size: 11px;
}

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
  margin: 0 0 4px;
  border-radius: 2px;
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
.build-graph-progress-info {
  margin-top: 10px;
}
.build-progress-wrap {
  height: 3px;
  background: var(--bg-overlay);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 5px;
}
.build-progress-bar {
  height: 100%;
  background: var(--text-primary);
  transition: width 0.4s ease;
}
.build-progress-label {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.build-graph-result {
  font-size: 12px;
  color: var(--positive);
  margin-top: 6px;
  font-weight: 600;
}
.build-graph-error {
  font-size: 12px;
  color: var(--negative);
  margin-top: 6px;
  font-weight: 500;
}

/* Upload (BYO) styles */
.upload-dropzone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-md);
  padding: 30px 20px;
  text-align: center;
  background: var(--bg-canvas);
  margin: 14px 0;
  transition: border-color var(--transition-fast), background var(--transition-fast);
}
.upload-dropzone.active {
  border-color: var(--text-primary);
  background: var(--bg-overlay);
}
.upload-icon {
  font-size: 28px; color: var(--text-muted); margin-bottom: 8px;
}
.upload-text {
  font-size: 13px; color: var(--text-secondary); line-height: 1.5;
}
.upload-text strong { color: var(--text-primary); }
.upload-hint { font-size: 11px; color: var(--text-faint); margin-top: 6px; }
.upload-selected { font-size: 12px; color: var(--text-secondary); }
.upload-filename { font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.upload-meta { color: var(--text-faint); font-size: 11px; margin-bottom: 8px; font-family: var(--font-mono); }
.link-btn {
  background: none; border: none; color: var(--text-primary);
  text-decoration: underline; cursor: pointer; padding: 0;
  font-size: inherit; font-family: inherit;
}
.upload-result {
  font-size: 12px; color: var(--text-secondary); margin-top: 14px;
  border-top: 1px solid var(--border-subtle); padding-top: 12px;
}
.upload-result-line { margin-bottom: 4px; }
.upload-errors {
  margin-top: 10px;
  background: rgba(239,68,68,0.06);
  border: 1px solid rgba(239,68,68,0.20);
  padding: 8px 12px; border-radius: var(--radius-sm);
}
.upload-errors-title { font-weight: 600; color: var(--negative); font-size: 11px; margin-bottom: 4px; }
.upload-errors ul { margin: 0; padding-left: 16px; font-size: 11px; }
</style>
