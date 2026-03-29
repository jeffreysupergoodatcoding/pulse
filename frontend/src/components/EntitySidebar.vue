<template>
  <div class="entity-section">
    <!-- Section header -->
    <div class="es-header">
      <span class="es-label">Entities</span>
      <router-link to="/" class="es-new-btn" title="Add new entity" aria-label="Add new entity">+</router-link>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="es-empty">
      <div class="es-loading-row" v-for="i in 3" :key="i">
        <div class="es-skeleton es-sk-avatar" />
        <div class="es-skeleton-block">
          <div class="es-skeleton es-sk-name" />
          <div class="es-skeleton es-sk-type" />
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-else-if="!entities.length" class="es-empty">
      <div class="es-empty-text">No entities yet.<br>Add one on the home screen.</div>
    </div>

    <!-- Entity list -->
    <ul v-else class="es-list">
      <li
        v-for="e in entities"
        :key="e.id"
        class="es-item"
        :class="{ active: isActive(e.id) }"
      >
        <!-- Main row -->
        <div class="es-row" @click="toggleExpand(e.id)">
          <span class="es-avatar" :style="{ background: avatarColor(e.name) }">
            {{ e.name.charAt(0).toUpperCase() }}
          </span>
          <div class="es-info">
            <span class="es-name">{{ e.name }}</span>
            <span class="es-type">{{ e.entity_type || e.type || 'entity' }}</span>
          </div>
          <span class="es-score" :class="sentimentBadge(e.sentiment_score)">
            {{ formatScore(e.sentiment_score) }}
          </span>
        </div>

        <!-- Sub-nav chips -->
        <div class="es-subnav" v-show="isActive(e.id) || expanded === e.id">
          <router-link :to="`/entity/${e.id}/ingest`"     class="es-chip">Ingest</router-link>
          <router-link :to="`/entity/${e.id}/graph`"      class="es-chip">Graph</router-link>
          <router-link :to="`/entity/${e.id}/personas`"   class="es-chip">Personas</router-link>
          <router-link :to="`/entity/${e.id}/simulation`" class="es-chip">Simulate</router-link>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { graph } from '../api/graph.js'

const route = useRoute()
const entities = ref([])
const loading = ref(true)
const expanded = ref(null)
let timer = null

async function load() {
  try {
    const r = await graph.listEntities()
    entities.value = r.data.entities || r.data || []
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function isActive(id) {
  return route.params.id === id
}

function toggleExpand(id) {
  expanded.value = expanded.value === id ? null : id
}

function sentimentBadge(score) {
  if (score == null) return 'score-neutral'
  if (score > 0.1) return 'score-pos'
  if (score < -0.1) return 'score-neg'
  return 'score-neutral'
}

function formatScore(score) {
  if (score == null) return '–'
  return (score >= 0 ? '+' : '') + score.toFixed(2)
}

const AVATAR_COLORS = [
  '#18181B', '#27272A', '#3F3F46', '#52525B',
  '#71717A', '#A1A1AA', '#6366F1', '#0EA5E9',
]

function avatarColor(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}

onMounted(() => {
  load()
  timer = setInterval(load, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.entity-section {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.es-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  flex-shrink: 0;
}
.es-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-faint);
  text-transform: uppercase;
  letter-spacing: 1.2px;
  font-family: var(--font-sans);
}
.es-new-btn {
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  background: var(--bg-overlay);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast);
  line-height: 1;
}
.es-new-btn:hover { background: var(--text-primary); color: #FFFFFF; }

/* Loading skeleton */
.es-empty {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.es-empty-text { font-size: 12px; color: var(--text-faint); line-height: 1.6; padding: 6px 0; }
.es-loading-row { display: flex; align-items: center; gap: 8px; }
.es-skeleton { background: var(--bg-overlay); border-radius: 3px; animation: shimmer 1.4s ease infinite; }
@keyframes shimmer {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}
.es-sk-avatar { width: 26px; height: 26px; border-radius: 6px; flex-shrink: 0; }
.es-skeleton-block { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.es-sk-name { height: 10px; width: 80%; }
.es-sk-type { height: 8px; width: 50%; }

.es-list {
  list-style: none;
  overflow-y: auto;
  flex: 1;
}

.es-item {
  border-bottom: 1px solid var(--border-subtle);
}
.es-item.active .es-row {
  background: var(--bg-overlay);
}
.es-item.active .es-name {
  color: var(--text-primary);
  font-weight: 600;
}

.es-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  cursor: pointer;
  transition: background var(--transition-fast);
  min-height: 44px;
}
.es-row:hover { background: var(--bg-hover); }

.es-avatar {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-family: var(--font-sans);
}

.es-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.es-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.2px;
}
.es-type {
  font-size: 10px;
  color: var(--text-faint);
  text-transform: capitalize;
  font-family: var(--font-mono);
}

.es-score {
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-sans);
  flex-shrink: 0;
  letter-spacing: -0.2px;
}
.es-score.score-pos { color: var(--positive); }
.es-score.score-neg { color: var(--negative); }
.es-score.score-neutral { color: var(--text-faint); }

.es-subnav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 12px 10px;
}
.es-chip {
  font-size: 11px;
  color: var(--text-muted);
  text-decoration: none;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
  font-weight: 500;
  letter-spacing: -0.1px;
}
.es-chip:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--border-default);
}
.es-chip.router-link-active {
  color: var(--text-primary);
  background: var(--text-primary);
  color: #FFFFFF;
  border-color: var(--text-primary);
  font-weight: 600;
}
</style>
