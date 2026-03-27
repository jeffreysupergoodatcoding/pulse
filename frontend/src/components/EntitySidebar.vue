<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">Entities</span>
      <router-link to="/" class="btn btn-sm btn-primary">+ New</router-link>
    </div>
    <div v-if="loading" class="text-muted" style="padding:12px">Loading…</div>
    <div v-else-if="!entities.length" class="text-muted" style="padding:12px;font-size:12px">
      No entities yet. Add one on the home screen.
    </div>
    <ul v-else class="entity-list">
      <li
        v-for="e in entities"
        :key="e.id"
        class="entity-item"
        :class="{ active: $route.params.id === e.id }"
      >
        <router-link :to="`/entity/${e.id}/graph`" class="entity-link">
          <span class="entity-name">{{ e.name }}</span>
          <span
            class="badge"
            :class="sentimentBadge(e.sentiment_score)"
          >{{ formatScore(e.sentiment_score) }}</span>
        </router-link>
        <nav class="entity-subnav">
          <router-link :to="`/entity/${e.id}/ingest`">Ingest</router-link>
          <router-link :to="`/entity/${e.id}/graph`">Graph</router-link>
          <router-link :to="`/entity/${e.id}/personas`">Personas</router-link>
          <router-link :to="`/entity/${e.id}/simulation`">Sim</router-link>
        </nav>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { graph } from '../api/graph.js'

const entities = ref([])
const loading = ref(true)
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

function sentimentBadge(score) {
  if (score == null) return 'badge-neutral'
  if (score > 0.1) return 'badge-positive'
  if (score < -0.1) return 'badge-negative'
  return 'badge-neutral'
}

function formatScore(score) {
  if (score == null) return '–'
  return (score >= 0 ? '+' : '') + score.toFixed(2)
}

onMounted(() => {
  load()
  timer = setInterval(load, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.sidebar {
  width: 100%; height: 100%;
  background: var(--bg-surface);
  display: flex; flex-direction: column; overflow-y: auto;
}
.sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.sidebar-title {
  font-size: 10px; font-weight: 600; color: var(--text-faint);
  text-transform: uppercase; letter-spacing: 1.5px;
}
.entity-list { list-style: none; }
.entity-item { border-bottom: 1px solid var(--border-subtle); }
.entity-item.active .entity-link { background: var(--bg-active); }
.entity-link {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 12px; text-decoration: none; color: var(--text-primary);
  font-size: 13px; transition: background var(--transition-fast);
}
.entity-link:hover { background: var(--bg-hover); }
.entity-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
.entity-subnav {
  display: flex; flex-wrap: wrap; gap: 2px; padding: 2px 8px 8px;
}
.entity-subnav a {
  font-size: 11px; color: var(--text-muted); text-decoration: none;
  padding: 2px 6px; border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.entity-subnav a:hover { color: var(--accent); background: var(--accent-light); }
.entity-subnav a.router-link-active { color: var(--accent); background: var(--accent-light); }
</style>
