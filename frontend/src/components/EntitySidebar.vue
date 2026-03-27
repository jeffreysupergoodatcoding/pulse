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
  width: 200px; flex-shrink: 0;
  background: #0d1117; border-right: 1px solid #2d3748;
  display: flex; flex-direction: column; overflow-y: auto;
}
.sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px; border-bottom: 1px solid #2d3748;
}
.sidebar-title { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.entity-list { list-style: none; }
.entity-item { border-bottom: 1px solid #1e2433; }
.entity-item.active .entity-link { background: #1a1f2e; }
.entity-link {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; text-decoration: none; color: #e2e8f0;
  font-size: 13px;
}
.entity-link:hover { background: #161b27; }
.entity-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entity-subnav {
  display: flex; gap: 0; padding: 0 8px 8px;
}
.entity-subnav a {
  font-size: 11px; color: #64748b; text-decoration: none;
  padding: 2px 6px; border-radius: 4px;
}
.entity-subnav a:hover, .entity-subnav a.router-link-active { color: #a78bfa; background: #1e2433; }
</style>
