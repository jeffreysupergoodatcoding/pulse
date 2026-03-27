<template>
  <div class="app-shell">
    <!-- 48px icon rail -->
    <nav class="icon-rail">
      <router-link to="/" class="rail-logo" title="PULSE Home">
        <span class="logo-hex">⬡</span>
      </router-link>
      <div class="rail-spacer" />
      <template v-if="$route.params.id">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="`/entity/${$route.params.id}/${item.path}`"
          class="rail-item"
          :class="{ active: $route.name === item.name }"
          :title="item.label"
        >
          <span class="rail-icon">{{ item.icon }}</span>
        </router-link>
      </template>
    </nav>

    <!-- 240px collapsible entity panel -->
    <aside class="entity-panel" :class="{ collapsed: panelCollapsed }">
      <EntitySidebar />
    </aside>

    <!-- Main area -->
    <div class="main-area">
      <!-- Top bar -->
      <header class="topbar">
        <button class="panel-toggle" @click="panelCollapsed = !panelCollapsed" title="Toggle panel">
          <span>☰</span>
        </button>
        <nav class="breadcrumb" v-if="$route.params.id">
          <router-link to="/" class="bc-link">PULSE</router-link>
          <span class="bc-sep">/</span>
          <router-link :to="`/entity/${$route.params.id}/graph`" class="bc-link">{{ entityName }}</router-link>
          <span class="bc-sep">/</span>
          <span class="bc-current">{{ routeLabel }}</span>
        </nav>
        <span v-else class="bc-home">PULSE Intelligence</span>
      </header>

      <!-- Content -->
      <main class="content-area">
        <ErrorBoundary>
          <router-view />
        </ErrorBoundary>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import EntitySidebar from './components/EntitySidebar.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'

const route = useRoute()
const panelCollapsed = ref(false)

const navItems = [
  { name: 'graph',      path: 'graph',      label: 'Graph',      icon: '◎' },
  { name: 'ingest',     path: 'ingest',     label: 'Ingest',     icon: '⬇' },
  { name: 'personas',   path: 'personas',   label: 'Personas',   icon: '◈' },
  { name: 'simulation', path: 'simulation', label: 'Simulation', icon: '▷' },
]

const LABELS = {
  graph: 'Graph', ingest: 'Ingest', personas: 'Personas',
  simulation: 'Simulation', report: 'Report', interact: 'Interact',
}

const routeLabel = computed(() => LABELS[route.name] || route.name || '')
const entityName = computed(() => {
  const id = route.params.id || ''
  return id.length > 20 ? id.slice(0, 20) + '…' : id
})
</script>

<style>
/* ── Shell layout ─────────────────────────────── */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-canvas);
  font-family: var(--font-sans);
}

/* ── Icon rail ────────────────────────────────── */
.icon-rail {
  width: var(--sidebar-icon-w);
  flex-shrink: 0;
  background: var(--bg-raised);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  z-index: 20;
}
.rail-logo {
  width: 36px; height: 36px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  text-decoration: none;
  margin-bottom: 8px;
}
.logo-hex { font-size: 22px; color: var(--accent); }
.rail-spacer { flex: 1; }
.rail-item {
  width: 36px; height: 36px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  text-decoration: none;
  color: var(--text-muted);
  margin-bottom: 4px;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.rail-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.rail-item.active { background: var(--accent-muted); color: var(--accent); }
.rail-icon { font-size: 15px; line-height: 1; }

/* ── Entity panel ─────────────────────────────── */
.entity-panel {
  width: var(--panel-w);
  flex-shrink: 0;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
  overflow-y: auto;
  overflow-x: hidden;
  transition: width var(--transition-base), opacity var(--transition-base);
}
.entity-panel.collapsed { width: 0; opacity: 0; }

/* ── Main area ────────────────────────────────── */
.main-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  min-width: 0;
}

/* ── Top bar ──────────────────────────────────── */
.topbar {
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.panel-toggle {
  width: 28px; height: 28px;
  border: none; background: none;
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
  font-size: 14px;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.panel-toggle:hover { background: var(--bg-hover); color: var(--text-primary); }
.breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.bc-link { color: var(--text-muted); text-decoration: none; }
.bc-link:hover { color: var(--text-primary); }
.bc-sep { color: var(--border-default); font-size: 11px; }
.bc-current { color: var(--text-primary); font-weight: 500; }
.bc-home { font-size: 13px; font-weight: 600; color: var(--accent); }

/* ── Content area ─────────────────────────────── */
.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: var(--bg-canvas);
}

/* ══════════════════════════════════════════════
   GLOBAL UTILITY CLASSES
══════════════════════════════════════════════ */

/* Cards */
.card {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

/* Buttons */
.btn {
  padding: 7px 14px;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: background var(--transition-fast), box-shadow var(--transition-fast);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn:hover { filter: brightness(0.96); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; filter: none; }
.btn-primary { background: var(--accent); color: var(--text-inverse); }
.btn-primary:hover { background: var(--accent-hover); filter: none; }
.btn-secondary {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}
.btn-secondary:hover { background: var(--bg-hover); border-color: var(--border-strong); filter: none; }
.btn-danger { background: var(--negative); color: var(--text-inverse); }
.btn-danger:hover { background: #b91c1c; filter: none; }
.btn-sm { padding: 4px 10px; font-size: 12px; border-radius: var(--radius-sm); }

/* Inputs */
input, select, textarea {
  background: var(--bg-raised);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  padding: 7px 11px;
  font-size: 13px;
  width: 100%;
  font-family: var(--font-sans);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-muted);
}
input::placeholder, textarea::placeholder { color: var(--text-faint); }
label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 4px;
  display: block;
}

/* Typography */
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }
.text-muted { color: var(--text-muted); font-size: 13px; }

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}
.badge-positive { background: var(--positive-bg); color: var(--positive-text); }
.badge-negative { background: var(--negative-bg); color: var(--negative-text); }
.badge-neutral  { background: var(--neutral-bg);  color: var(--neutral-text); }

/* Layout helpers */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.flex   { display: flex; }
.gap-2  { gap: 8px; }
.gap-3  { gap: 12px; }
.mt-2   { margin-top: 8px; }
.mt-3   { margin-top: 12px; }
.mt-4   { margin-top: 16px; }
</style>
