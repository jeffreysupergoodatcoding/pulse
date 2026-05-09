<template>
  <div class="app-shell">
    <!-- Unified sidebar -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <!-- Logo row -->
      <div class="sb-logo">
        <router-link to="/" class="sb-logo-link">
          <div class="logo-mark" aria-hidden="true">
            <div class="logo-bar" style="height:6px"></div>
            <div class="logo-bar" style="height:12px"></div>
            <div class="logo-bar" style="height:8px"></div>
            <div class="logo-bar" style="height:15px"></div>
            <div class="logo-bar" style="height:5px"></div>
          </div>
          <span class="logo-text" v-show="!sidebarCollapsed">pulse</span>
        </router-link>
        <button class="sb-collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'">
          <span>{{ sidebarCollapsed ? '›' : '‹' }}</span>
        </button>
      </div>

      <!-- Entity list (middle, scrollable) -->
      <div class="sb-entities" v-show="!sidebarCollapsed">
        <EntitySidebar />
      </div>

      <!-- Nav items pinned to bottom -->
      <nav class="sb-nav" v-if="$route.params.id">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="`/entity/${$route.params.id}/${item.path}`"
          class="sb-nav-item"
          :title="item.label"
        >
          <span class="sb-nav-icon">{{ item.icon }}</span>
          <span class="sb-nav-label" v-show="!sidebarCollapsed">{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>

    <!-- Main area -->
    <div class="main-area">
      <!-- Topbar -->
      <header class="topbar">
        <nav class="breadcrumb" v-if="$route.params.id">
          <router-link to="/" class="bc-link">pulse</router-link>
          <span class="bc-sep">/</span>
          <router-link :to="`/entity/${$route.params.id}/graph`" class="bc-link">{{ entityName }}</router-link>
          <span class="bc-sep">/</span>
          <span class="bc-current">{{ routeLabel }}</span>
        </nav>
        <div v-else class="bc-home-wrap">
          <div class="logo-mark logo-mark-sm" aria-hidden="true">
            <div class="logo-bar" style="height:5px"></div>
            <div class="logo-bar" style="height:9px"></div>
            <div class="logo-bar" style="height:6px"></div>
            <div class="logo-bar" style="height:11px"></div>
            <div class="logo-bar" style="height:4px"></div>
          </div>
          <span class="bc-home">PULSE Intelligence</span>
        </div>
      </header>

      <!-- Content -->
      <main class="content-area" :class="{ 'full-bleed': isFullBleed, 'no-dot-grid': noDotGrid }">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import EntitySidebar from './components/EntitySidebar.vue'

const route = useRoute()
const sidebarCollapsed = ref(false)

const isFullBleed = computed(() => ['simulation', 'graph'].includes(route.name))
const noDotGrid = computed(() => route.name === 'personas')

const navItems = [
  { name: 'ingest',     path: 'ingest',     label: 'Ingest',   icon: '⬇' },
  { name: 'graph',      path: 'graph',      label: 'Graph',    icon: '◎' },
  { name: 'personas',   path: 'personas',   label: 'Personas', icon: '◈' },
  { name: 'simulation', path: 'simulation', label: 'Simulate', icon: '▷' },
  { name: 'audience',   path: 'audience',   label: 'Audience', icon: '◐' },
]

const LABELS = {
  graph: 'Graph', ingest: 'Ingest', personas: 'Personas',
  simulation: 'Simulate', report: 'Report', interact: 'Chat',
  audience: 'Audience', home: 'Home',
}

const routeLabel = computed(() => LABELS[route.name] || route.name || '')
const entityName = computed(() => {
  const id = route.params.id || ''
  return id.length > 20 ? id.slice(0, 20) + '…' : id
})
</script>

<style>
/* ── Reset & base ─────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

/* ── Shell layout ─────────────────────────────── */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-canvas);
  font-family: var(--font-sans);
}

/* ── Sidebar ──────────────────────────────────── */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-base);
  overflow: hidden;
  z-index: 20;
}
.sidebar.collapsed { width: 52px; }

/* Logo row */
.sb-logo {
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  gap: 8px;
}
.sb-logo-link {
  display: flex;
  align-items: center;
  gap: 9px;
  text-decoration: none;
  flex: 1;
  min-width: 0;
}

/* Waveform logo mark */
.logo-mark {
  display: flex;
  align-items: flex-end;
  gap: 2.5px;
  height: 18px;
  flex-shrink: 0;
}
.logo-mark-sm {
  height: 14px;
}
.logo-bar {
  width: 3px;
  background: var(--text-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  white-space: nowrap;
  overflow: hidden;
  font-family: var(--font-sans);
}

.sb-collapse-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-faint);
  font-size: 16px;
  flex-shrink: 0;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.sb-collapse-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

/* Entity section */
.sb-entities {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
}

/* Nav items */
.sb-nav {
  padding: 8px 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.sb-nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 8px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  transition: background var(--transition-fast), color var(--transition-fast);
  white-space: nowrap;
  min-height: 36px;
  letter-spacing: -0.1px;
}
.sb-nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.sb-nav-item.router-link-active {
  background: var(--accent-muted);
  color: var(--text-primary);
  font-weight: 600;
}
.sb-nav-icon { font-size: 13px; flex-shrink: 0; width: 18px; text-align: center; }
.sb-nav-label { overflow: hidden; }

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
  padding: 0 20px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.bc-link { color: var(--text-muted); text-decoration: none; font-weight: 400; }
.bc-link:hover { color: var(--text-primary); }
.bc-sep { color: var(--border-default); font-size: 11px; }
.bc-current { color: var(--text-primary); font-weight: 600; letter-spacing: -0.1px; }

.bc-home-wrap { display: flex; align-items: center; gap: 8px; }
.bc-home { font-size: 13px; font-weight: 500; color: var(--text-muted); letter-spacing: -0.1px; }

/* ── Content area ─────────────────────────────── */
.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
  background: var(--bg-canvas);
  position: relative;
}
/* Dot grid overlay on canvas */
.content-area::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: radial-gradient(circle, var(--dot-color) 1px, transparent 1px);
  background-size: var(--dot-size) var(--dot-size);
  z-index: 0;
}
.content-area > * { position: relative; z-index: 1; }

.content-area.full-bleed {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.content-area.full-bleed > * { flex: 1; min-height: 0; }
.content-area.full-bleed::before { display: none; }
.content-area.no-dot-grid::before { display: none; }

/* ══════════════════════════════════════════════
   GLOBAL UTILITY CLASSES
══════════════════════════════════════════════ */

/* View headers */
.view-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}
.view-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 3px;
  letter-spacing: -0.6px;
  font-family: var(--font-sans);
  line-height: 1.2;
}
.view-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
  font-weight: 400;
}

/* Cards */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

/* Buttons */
.btn {
  padding: 8px 16px;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: background var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-sans);
  letter-spacing: -0.1px;
}
.btn:active:not(:disabled) { transform: scale(0.985); }
.btn:disabled { opacity: 0.38; cursor: not-allowed; }

.btn-primary { background: var(--text-primary); color: #FFFFFF; }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }

.btn-secondary {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}
.btn-secondary:hover:not(:disabled) { background: var(--bg-hover); border-color: var(--border-strong); }

.btn-danger { background: var(--negative); color: #FFFFFF; }
.btn-danger:hover:not(:disabled) { background: #B91C1C; }

.btn-sm { padding: 5px 11px; font-size: 12px; border-radius: var(--radius-sm); }

/* Inputs */
input, select, textarea {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  padding: 8px 12px;
  font-size: 13px;
  width: 100%;
  font-family: var(--font-sans);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  letter-spacing: -0.1px;
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--text-primary);
  box-shadow: var(--shadow-focus);
}
input::placeholder, textarea::placeholder { color: var(--text-faint); }
label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 5px;
  display: block;
  letter-spacing: 0.1px;
}

/* Typography */
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 14px;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.text-muted { color: var(--text-muted); font-size: 13px; }

/* Badges */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-sans);
  letter-spacing: 0.1px;
}
.badge-positive { background: var(--positive-bg); color: var(--positive-text); }
.badge-negative { background: var(--negative-bg); color: var(--negative-text); }
.badge-neutral  { background: var(--neutral-bg);  color: var(--neutral-text); }

/* Status pills */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-family: var(--font-sans);
}
.status-pill::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.status-running   { background: var(--positive-bg); color: var(--positive); }
.status-idle      { background: var(--neutral-bg);  color: var(--neutral-text); }
.status-error     { background: var(--negative-bg); color: var(--negative); }
.status-completed { background: var(--accent-muted); color: var(--text-primary); }
.status-paused    { background: var(--warning-bg); color: var(--warning); }
.status-stopped   { background: var(--neutral-bg);  color: var(--neutral-text); }

/* Pane header */
.pane-header {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--text-faint);
  padding: 10px 16px 8px;
  flex-shrink: 0;
  font-family: var(--font-sans);
}

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
