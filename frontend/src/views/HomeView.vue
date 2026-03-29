<template>
  <div class="home-root">
    <!-- Decorative dot-grid accent (top-right) -->
    <div class="home-dot-accent" aria-hidden="true" />

    <!-- Header -->
    <div class="view-header">
      <div>
        <h1 class="view-title">Entities</h1>
        <p class="view-subtitle">Track brands, people, and influencers across social platforms</p>
      </div>
      <button class="btn btn-primary" @click="drawerOpen = true">+ New Entity</button>
    </div>

    <!-- Entity grid -->
    <div v-if="entities.length" class="entity-grid">
      <div
        v-for="e in entities"
        :key="e.id"
        class="entity-card"
        @click="navigateTo(e.id)"
      >
        <!-- Card top -->
        <div class="ec-top">
          <span class="ec-avatar" :style="{ background: avatarColor(e.name) }">
            {{ e.name.charAt(0).toUpperCase() }}
          </span>
          <div class="ec-info">
            <div class="ec-name">{{ e.name }}</div>
            <div class="ec-type">{{ e.entity_type || e.type || 'Entity' }}</div>
          </div>
          <span class="badge" :class="sentimentBadge(e.sentiment_score)">
            {{ formatScore(e.sentiment_score) }}
          </span>
        </div>

        <!-- Description -->
        <div v-if="e.description" class="ec-desc">{{ truncate(e.description, 90) }}</div>

        <!-- ID chip -->
        <div class="ec-id">{{ e.id?.slice(0, 12) }}…</div>

        <!-- Action buttons -->
        <div class="ec-actions" @click.stop>
          <router-link :to="`/entity/${e.id}/simulation`" class="btn btn-primary btn-sm">▶ Simulate</router-link>
          <router-link :to="`/entity/${e.id}/graph`" class="btn btn-secondary btn-sm">Graph</router-link>
          <router-link :to="`/entity/${e.id}/personas`" class="btn btn-secondary btn-sm">Personas</router-link>
        </div>
      </div>
    </div>

    <div v-else-if="!loadingEntities" class="empty-state">
      <div class="empty-dot-grid" aria-hidden="true" />
      <div class="empty-icon">◎</div>
      <div class="empty-title">No entities yet</div>
      <div class="empty-sub">Create your first entity to start tracking and simulating sentiment.</div>
      <button class="btn btn-primary" @click="drawerOpen = true">+ New Entity</button>
    </div>

    <!-- New Entity Drawer -->
    <div v-if="drawerOpen" class="drawer-overlay" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <div class="drawer-header-left">
            <span class="drawer-title">New Entity</span>
            <span class="drawer-subtitle">Define a brand, person, or influencer to track</span>
          </div>
          <button class="drawer-close" @click="drawerOpen = false" aria-label="Close">×</button>
        </div>

        <div class="drawer-body">
          <div class="grid-2">
            <div>
              <label>Name *</label>
              <input v-model="form.name" placeholder="Nike, Taylor Swift…" />
            </div>
            <div>
              <label>Type</label>
              <select v-model="form.entity_type">
                <option value="brand">Brand</option>
                <option value="person">Person</option>
                <option value="influencer">Influencer</option>
              </select>
            </div>
          </div>

          <div class="mt-3">
            <label>Description</label>
            <input v-model="form.description" placeholder="Brief description…" />
          </div>

          <div class="mt-3">
            <label>Keywords <span class="hint">(comma-separated)</span></label>
            <input v-model="form.keywords_raw" placeholder="nike, air max, sneakers" />
          </div>

          <div class="drawer-section-label">Source Config</div>

          <div class="grid-2">
            <div>
              <label>Reddit subreddits</label>
              <input v-model="form.reddit_subreddits" placeholder="sneakers, nba" />
            </div>
            <div>
              <label>Twitter queries</label>
              <input v-model="form.twitter_queries" placeholder="#Nike, Nike shoes" />
            </div>
          </div>

          <div v-if="error" class="drawer-error">{{ error }}</div>
        </div>

        <div class="drawer-footer">
          <button class="btn btn-secondary" @click="drawerOpen = false">Cancel</button>
          <button class="btn btn-primary" :disabled="!form.name || saving" @click="addEntity">
            {{ saving ? 'Creating…' : 'Create Entity' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { graph as graphApi } from '../api/graph.js'

const router = useRouter()
const entities = ref([])
const loadingEntities = ref(true)
const saving = ref(false)
const error = ref('')
const drawerOpen = ref(false)

const form = ref({
  name: '', entity_type: 'brand', description: '',
  keywords_raw: '', reddit_subreddits: '', twitter_queries: '',
})

// Subtle neutral palette for avatars — B&W theme
const AVATAR_COLORS = [
  '#18181B', '#27272A', '#3F3F46', '#52525B',
  '#71717A', '#A1A1AA', '#D4D4D8', '#1C1C1E',
]

function avatarColor(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}

function navigateTo(id) {
  router.push(`/entity/${id}/graph`)
}

async function loadEntities() {
  loadingEntities.value = true
  try {
    const r = await graphApi.listEntities()
    entities.value = r.data.entities || r.data || []
  } finally {
    loadingEntities.value = false
  }
}

async function addEntity() {
  error.value = ''
  saving.value = true
  try {
    const keywords = form.value.keywords_raw.split(',').map(s => s.trim()).filter(Boolean)
    const subreddits = form.value.reddit_subreddits.split(',').map(s => s.trim()).filter(Boolean)
    const twitter_queries = form.value.twitter_queries.split(',').map(s => s.trim()).filter(Boolean)
    await graphApi.createEntity({
      name: form.value.name,
      entity_type: form.value.entity_type,
      description: form.value.description,
      keywords,
      source_config: {
        reddit: { subreddits },
        twitter: { queries: twitter_queries },
      },
    })
    form.value = { name: '', entity_type: 'brand', description: '', keywords_raw: '', reddit_subreddits: '', twitter_queries: '' }
    drawerOpen.value = false
    await loadEntities()
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    saving.value = false
  }
}

function sentimentBadge(score) {
  if (score == null) return 'badge-neutral'
  return score > 0.1 ? 'badge-positive' : score < -0.1 ? 'badge-negative' : 'badge-neutral'
}
function formatScore(s) {
  if (s == null) return '–'
  return (s >= 0 ? '+' : '') + Number(s).toFixed(2)
}
function truncate(s, n) { return s?.length > n ? s.slice(0, n) + '…' : s }

onMounted(loadEntities)
</script>

<style scoped>
.home-root {
  position: relative;
}

/* Decorative dot-grid accent (top-right corner of page) */
.home-dot-accent {
  position: absolute;
  top: -28px;
  right: -28px;
  width: 380px;
  height: 220px;
  background-image: radial-gradient(circle, rgba(0,0,0,0.11) 1px, transparent 1px);
  background-size: 18px 18px;
  -webkit-mask-image: radial-gradient(ellipse 70% 80% at 75% 25%, black 20%, transparent 70%);
  mask-image: radial-gradient(ellipse 70% 80% at 75% 25%, black 20%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

/* Entity grid */
.entity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  position: relative;
  z-index: 1;
}

.entity-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: box-shadow var(--transition-base), transform var(--transition-base), border-color var(--transition-base);
}
.entity-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
  border-left-color: var(--text-primary);
  border-color: var(--border-default);
}

.ec-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ec-avatar {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-family: var(--font-sans);
}
.ec-info {
  flex: 1;
  min-width: 0;
}
.ec-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.3px;
}
.ec-type {
  font-size: 10px;
  color: var(--text-faint);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-family: var(--font-mono);
  margin-top: 1px;
}

.ec-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.55;
}

.ec-id {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-faint);
  letter-spacing: 0;
}

.ec-actions {
  display: flex;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 80px 24px;
  gap: 12px;
  position: relative;
}
.empty-dot-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(0,0,0,0.07) 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
  border-radius: var(--radius-lg);
}
.empty-icon { font-size: 36px; color: var(--border-strong); position: relative; }
.empty-title { font-size: 17px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.3px; position: relative; }
.empty-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 6px; max-width: 340px; position: relative; line-height: 1.6; }

/* Drawer */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.25);
  backdrop-filter: blur(4px);
  z-index: 100;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.drawer {
  width: 480px;
  max-width: 100vw;
  height: 100vh;
  background: var(--bg-surface);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  animation: slideIn 0.18s ease;
  border-left: 1px solid var(--border-subtle);
}
@keyframes slideIn {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.drawer-header-left { display: flex; flex-direction: column; gap: 2px; }
.drawer-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.drawer-subtitle {
  font-size: 12px;
  color: var(--text-muted);
}
.drawer-close {
  width: 28px; height: 28px;
  background: none; border: none; cursor: pointer;
  font-size: 20px; color: var(--text-faint);
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
  margin-top: 2px;
}
.drawer-close:hover { background: var(--bg-hover); color: var(--text-primary); }

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.drawer-section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--text-faint);
  margin: 22px 0 10px;
  font-family: var(--font-sans);
}

.hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-faint);
}

.drawer-error {
  margin-top: 12px;
  font-size: 12px;
  color: var(--negative);
  padding: 8px 12px;
  background: var(--negative-bg);
  border-radius: var(--radius-md);
  border: 1px solid rgba(220,38,38,0.15);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
</style>
