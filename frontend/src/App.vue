<template>
  <div class="app-shell">
    <header class="topbar">
      <span class="logo">⬡ PULSE</span>
      <nav class="breadcrumb" v-if="$route.params.id">
        <router-link :to="`/entity/${$route.params.id}/graph`">{{ $route.params.id }}</router-link>
        <span class="sep">›</span>
        <span>{{ routeLabel }}</span>
      </nav>
    </header>
    <div class="main-layout">
      <EntitySidebar />
      <main class="content">
        <ErrorBoundary>
          <router-view />
        </ErrorBoundary>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import EntitySidebar from './components/EntitySidebar.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'

const route = useRoute()
const LABELS = {
  graph: 'Graph', ingest: 'Ingest', personas: 'Personas',
  simulation: 'Simulation', report: 'Report', interact: 'Interact',
}
const routeLabel = computed(() => {
  const name = route.name || ''
  return LABELS[name] || name
})
</script>

<style>
.app-shell { display: flex; flex-direction: column; height: 100vh; }

.topbar {
  display: flex; align-items: center; gap: 16px;
  padding: 0 20px; height: 48px;
  background: #161b27; border-bottom: 1px solid #2d3748;
  flex-shrink: 0;
}
.logo { font-weight: 700; font-size: 16px; color: #7c3aed; letter-spacing: 2px; }
.breadcrumb { font-size: 13px; color: #94a3b8; display: flex; align-items: center; gap: 6px; }
.breadcrumb a { color: #a78bfa; text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.sep { color: #4b5563; }

.main-layout { display: flex; flex: 1; overflow: hidden; }
.content { flex: 1; overflow-y: auto; padding: 24px; }

/* Global styles */
.card { background: #161b27; border: 1px solid #2d3748; border-radius: 8px; padding: 20px; }
.btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; transition: opacity .15s; }
.btn:hover { opacity: .85; }
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-secondary { background: #2d3748; color: #e2e8f0; }
.btn-danger { background: #dc2626; color: #fff; }
.btn-sm { padding: 4px 10px; font-size: 12px; }

input, select, textarea {
  background: #1e2433; border: 1px solid #374151; border-radius: 6px;
  color: #e2e8f0; padding: 8px 12px; font-size: 13px; width: 100%;
}
input:focus, select:focus, textarea:focus {
  outline: none; border-color: #7c3aed;
}
label { font-size: 12px; color: #94a3b8; margin-bottom: 4px; display: block; }

.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #f1f5f9; }
.text-muted { color: #64748b; font-size: 13px; }
.badge {
  display: inline-flex; align-items: center; padding: 2px 8px;
  border-radius: 9999px; font-size: 11px; font-weight: 600;
}
.badge-positive { background: #14532d; color: #4ade80; }
.badge-negative { background: #450a0a; color: #f87171; }
.badge-neutral  { background: #1e2433; color: #94a3b8; }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.flex { display: flex; }
.gap-2 { gap: 8px; }
.gap-3 { gap: 12px; }
.mt-2 { margin-top: 8px; }
.mt-3 { margin-top: 12px; }
.mt-4 { margin-top: 16px; }
</style>
