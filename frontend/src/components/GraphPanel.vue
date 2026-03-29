<template>
  <div class="graph-wrap">
    <!-- Dot-grid background overlay -->
    <div class="graph-dot-grid" />

    <div ref="containerRef" class="graph-container" />

    <!-- Empty state -->
    <div v-if="!hasData" class="graph-empty">
      <div class="empty-inner">
        <span class="empty-icon">◎</span>
        <div>No graph data. Run <strong>Build Graph</strong> in Ingest first.</div>
      </div>
    </div>

    <!-- Stats chip -->
    <div v-if="hasData" class="graph-stats">
      {{ nodes.length }} nodes · {{ edges.length }} edges
    </div>

    <!-- Controls toolbar (top-right) -->
    <div class="graph-toolbar">
      <button class="ctrl-btn" @click="resetCamera" title="Reset view">⌖</button>
      <button class="ctrl-btn" :class="{ active: autoRotate }" @click="toggleRotate" title="Auto-rotate">↻</button>
      <button class="ctrl-btn" @click="fitGraph" title="Fit to screen">⤢</button>
    </div>

    <!-- Node/edge relationship popup -->
    <div class="graph-info-panel" :class="{ visible: !!selectedNode }">
      <button class="info-close" @click="selectedNode = null" aria-label="Close">×</button>
      <div v-if="selectedNode">
        <div class="info-title">Relationship</div>
        <div class="info-path" v-if="selectedNode.fromLabel">
          {{ selectedNode.fromLabel }} → {{ selectedNode.relation }} → {{ selectedNode.label }}
        </div>
        <div class="info-field-group">
          <div class="info-field">
            <span class="info-field-label">Label</span>
            <span class="info-field-value">{{ selectedNode.label || selectedNode.id }}</span>
          </div>
          <div class="info-field">
            <span class="info-field-label">Type</span>
            <span class="info-field-value">{{ selectedNode.type || 'Node' }}</span>
          </div>
          <div class="info-field" v-if="selectedNode.id">
            <span class="info-field-label">ID</span>
            <span class="info-field-value mono">{{ selectedNode.id?.slice(0, 28) }}</span>
          </div>
          <div class="info-field">
            <span class="info-field-label">Connections</span>
            <span class="info-field-value">{{ connectionCount(selectedNode) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend (bottom-left pill chips) -->
    <div class="graph-legend">
      <span class="leg-chip" style="--c:#6366F1"><span class="leg-dot" />Entity</span>
      <span class="leg-chip" style="--c:#0EA5E9"><span class="leg-dot" />Topic</span>
      <span class="leg-chip" style="--c:#10B981"><span class="leg-dot" />Source</span>
      <span class="leg-chip" style="--c:#EF4444"><span class="leg-dot" />Media</span>
      <span class="leg-chip" style="--c:#8B5CF6"><span class="leg-dot" />Gov/Policy</span>
      <span class="leg-chip" style="--c:#F97316"><span class="leg-dot" />Executive</span>
      <span class="leg-chip" style="--c:#EC4899"><span class="leg-dot" />Product</span>
      <span class="leg-chip" style="--c:#14B8A6"><span class="leg-dot" />Finance</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ForceGraph3D from '3d-force-graph'
import { graph as graphApi } from '../api/graph.js'

const props = defineProps({ entityId: { type: String, required: true } })

const containerRef = ref(null)
const nodes = ref([])
const edges = ref([])
const hasData = ref(false)
const autoRotate = ref(false)
const selectedNode = ref(null)

let graphInstance = null
let pollTimer = null
let rotateHandle = null
let resizeObserver = null

// Z-plane depths per node type — 3 distinct visual planes
const PLANE_Z = {
  Brand: 0, Person: 0, Influencer: 0, Company: 0, TechExecutive: 0,
  Topic: 150,
  Unknown: 300, Source: 300, Event: 300, Community: 300, Product: 300,
  Organization: 300, MediaOutlet: 300, GovernmentAgency: 300,
  InvestorInstitution: 300, PolicyMaker: 300, DeveloperCommunity: 300,
}

// Node colors — multi-color for rich "hairball" visualization
const NODE_COLOR = {
  Brand: '#6366F1', Person: '#6366F1', Influencer: '#6366F1', Company: '#6366F1',
  Topic: '#0EA5E9',
  Unknown: '#10B981', Source: '#10B981', Event: '#F59E0B',
  Community: '#10B981', Product: '#EC4899',
  Organization: '#3B82F6',
  MediaOutlet: '#EF4444',
  GovernmentAgency: '#8B5CF6',
  InvestorInstitution: '#14B8A6',
  PolicyMaker: '#8B5CF6',
  DeveloperCommunity: '#10B981',
  TechExecutive: '#F97316',
}

function getZ(type) { return PLANE_Z[type] ?? 300 }
function getColor(type) { return NODE_COLOR[type] || '#10B981' }
function getSize(type) {
  if (type === 'Brand') return 8
  if (type === 'Person' || type === 'Influencer') return 5
  return 3
}

function connectionCount(node) {
  if (!node) return 0
  return edges.value.filter(e => e.source === node.id || e.target === node.id).length
}

function initGraph() {
  if (!containerRef.value) return
  const w = containerRef.value.clientWidth || 800
  const h = containerRef.value.clientHeight || 600

  graphInstance = ForceGraph3D({ controlType: 'orbit' })(containerRef.value)
    .width(w)
    .height(h)
    .backgroundColor('#FFFFFF')
    .showNavInfo(false)
    // Links
    .linkColor(() => 'rgba(150,158,180,0.25)')
    .linkWidth(0.5)
    .linkDirectionalParticles(1)
    .linkDirectionalParticleWidth(1.2)
    .linkDirectionalParticleColor(() => 'rgba(99,102,241,0.45)')
    // Nodes
    .nodeColor(d => getColor(d.type))
    .nodeVal(d => getSize(d.type))
    .nodeLabel(d => `
      <div style="
        background:#fff;border:1px solid #E2E6EF;border-radius:10px;
        padding:8px 12px;font-size:12px;color:#111827;
        box-shadow:0 4px 16px rgba(15,23,42,0.1);
        font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;
        max-width:220px;line-height:1.5">
        <strong style="font-size:13px">${d.label || d.id}</strong><br/>
        <span style="color:#9CA3AF;font-size:10px;text-transform:uppercase;letter-spacing:0.5px">${d.type || 'Node'}</span>
      </div>
    `)
    .onNodeClick(node => {
      selectedNode.value = {
        ...node,
        fromLabel: null,
        relation: null,
      }
    })
    .onEngineStop(() => {
      // Only zoom when there is actual data — onEngineStop also fires at init with empty graph
      if (!graphInstance || !hasData.value) return
      graphInstance.zoomToFit(800, 80)
    })

  // Free 3D layout — no z-plane constraint so the graph orbits in true 3D space
  graphInstance.d3Force('z-plane', null)

  // Denser clustering: moderate repulsion, short links
  graphInstance.d3Force('charge')?.strength(-120)
  graphInstance.d3Force('link')?.distance(30).strength(0.8)

  renderGraph()
}

function renderGraph() {
  if (!graphInstance) return
  hasData.value = nodes.value.length > 0
  if (!hasData.value) return

  graphInstance.graphData({
    nodes: nodes.value.map(n => ({
      ...n,
      id: n.id,
      label: n.label || n.id,
      type: n.type || 'Unknown',
    })),
    links: edges.value.map(e => ({
      source: e.source,
      target: e.target,
      label: e.relation || e.label || '',
    })),
  })
}

async function loadData() {
  if (!props.entityId) return
  try {
    const r = await graphApi.getData(props.entityId)
    const data = r.data
    nodes.value = data.nodes || []
    edges.value = data.edges || data.links || []
    renderGraph()
  } catch { /* ignore */ }
}

function resetCamera() {
  graphInstance?.zoomToFit(600, 40)
}

function fitGraph() {
  graphInstance?.zoomToFit(400)
}

function toggleRotate() {
  autoRotate.value = !autoRotate.value
  if (autoRotate.value) {
    let angle = 0
    rotateHandle = setInterval(() => {
      angle += 0.004
      const r = 600
      graphInstance?.cameraPosition({
        x: r * Math.sin(angle),
        y: 0,
        z: r * Math.cos(angle),
      })
    }, 16)
  } else {
    clearInterval(rotateHandle)
  }
}

watch(() => props.entityId, () => {
  nodes.value = []
  edges.value = []
  hasData.value = false
  selectedNode.value = null
  loadData()
})

onMounted(async () => {
  // Wait for the split-pane layout to fully resolve before reading container dimensions
  await nextTick()
  initGraph()
  loadData()
  pollTimer = setInterval(loadData, 10000)

  // Keep the graph canvas sized correctly if the panel is resized
  resizeObserver = new ResizeObserver(() => {
    if (!containerRef.value || !graphInstance) return
    graphInstance
      .width(containerRef.value.clientWidth)
      .height(containerRef.value.clientHeight)
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(rotateHandle)
  resizeObserver?.disconnect()
  if (graphInstance) {
    try { graphInstance._destructor?.() } catch { /* ignore */ }
    graphInstance = null
  }
})
</script>

<style scoped>
.graph-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  background: #FFFFFF;
  overflow: hidden;
}

/* Dot-grid overlay — positioned ABOVE the 3D canvas */
.graph-dot-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(0,0,0,0.09) 1px, transparent 1px);
  background-size: 22px 22px;
  pointer-events: none;
  z-index: 2;
}

.graph-container { width: 100%; height: 100%; position: relative; z-index: 1; }

/* Empty state */
.graph-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  pointer-events: none; z-index: 5;
}
.empty-inner {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  color: var(--text-faint); font-size: 13px; text-align: center;
  background: rgba(255,255,255,0.94);
  backdrop-filter: blur(8px);
  padding: 24px 32px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-md);
  font-family: var(--font-sans);
}
.empty-icon { font-size: 32px; color: var(--border-strong); }

/* Stats chip */
.graph-stats {
  position: absolute; top: 12px; left: 14px;
  font-size: 11px; color: var(--text-muted);
  background: rgba(255,255,255,0.94);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  padding: 4px 12px;
  box-shadow: var(--shadow-sm);
  z-index: 5;
  font-family: var(--font-sans);
  font-weight: 500;
  letter-spacing: -0.1px;
}

/* Controls toolbar (top-right) */
.graph-toolbar {
  position: absolute; top: 12px; right: 14px;
  display: flex; gap: 4px;
  z-index: 5;
}
.ctrl-btn {
  width: 32px; height: 32px;
  border: 1px solid var(--border-default);
  background: rgba(255,255,255,0.94);
  backdrop-filter: blur(10px);
  border-radius: var(--radius-md);
  cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
  box-shadow: var(--shadow-sm);
  font-family: var(--font-sans);
}
.ctrl-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-strong); }
.ctrl-btn.active { background: var(--text-primary); color: #FFFFFF; border-color: var(--text-primary); }

/* Node info panel */
.graph-info-panel {
  position: absolute;
  top: 54px;
  right: 14px;
  width: 272px;
  background: rgba(255,255,255,0.98);
  backdrop-filter: blur(14px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: var(--shadow-lg);
  transform: translateX(300px);
  opacity: 0;
  transition: transform var(--transition-base), opacity var(--transition-base);
  z-index: 10;
  font-family: var(--font-sans);
}
.graph-info-panel.visible {
  transform: translateX(0);
  opacity: 1;
}
.info-close {
  position: absolute; top: 10px; right: 12px;
  background: none; border: none; cursor: pointer;
  font-size: 18px; color: var(--text-faint); line-height: 1;
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
}
.info-close:hover { color: var(--text-primary); background: var(--bg-hover); }
.info-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}
.info-path {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 12px;
  padding: 6px 8px;
  background: var(--bg-overlay);
  border-radius: var(--radius-sm);
  word-break: break-all;
  border: 1px solid var(--border-subtle);
  font-family: var(--font-mono);
}
.info-field-group { border-top: 1px solid var(--border-subtle); padding-top: 10px; }
.info-field {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px;
}
.info-field:last-child { border-bottom: none; }
.info-field-label { color: var(--text-faint); flex-shrink: 0; font-size: 11px; }
.info-field-value { color: var(--text-primary); font-weight: 500; text-align: right; word-break: break-all; }
.info-field-value.mono { font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); }

/* Legend (bottom-left) */
.graph-legend {
  position: absolute; bottom: 14px; left: 14px;
  display: flex; gap: 6px; flex-wrap: wrap;
  z-index: 5;
}
.leg-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  background: rgba(255,255,255,0.94);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  box-shadow: var(--shadow-sm);
  font-family: var(--font-sans);
  letter-spacing: -0.1px;
}
.leg-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--c);
  flex-shrink: 0;
}
</style>
