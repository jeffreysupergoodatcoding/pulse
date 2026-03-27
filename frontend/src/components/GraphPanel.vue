<template>
  <div class="graph-wrap">
    <div ref="containerRef" class="graph-container" />

    <div v-if="!hasData" class="graph-empty">
      <div class="empty-inner">
        <span class="empty-icon">◎</span>
        <div>No graph data. Run <strong>Build Graph</strong> in Ingest first.</div>
      </div>
    </div>

    <!-- Plane legend -->
    <div class="graph-legend">
      <span class="leg-item">
        <span class="leg-dot" style="background:#6366F1" />
        Entity / Person
        <span class="leg-plane">Plane 1</span>
      </span>
      <span class="leg-item">
        <span class="leg-dot" style="background:#0EA5E9" />
        Topic
        <span class="leg-plane">Plane 2</span>
      </span>
      <span class="leg-item">
        <span class="leg-dot" style="background:#10B981" />
        Source
        <span class="leg-plane">Plane 3</span>
      </span>
    </div>

    <!-- Controls -->
    <div class="graph-controls">
      <button class="ctrl-btn" @click="resetCamera" title="Reset view">⌖</button>
      <button class="ctrl-btn" :class="{ active: autoRotate }" @click="toggleRotate" title="Auto-rotate">↻</button>
    </div>

    <!-- Stats badge -->
    <div v-if="hasData" class="graph-stats">
      {{ nodes.length }} nodes · {{ edges.length }} edges
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import ForceGraph3D from '3d-force-graph'
import { graph as graphApi } from '../api/graph.js'

const props = defineProps({ entityId: { type: String, required: true } })

const containerRef = ref(null)
const nodes = ref([])
const edges = ref([])
const hasData = ref(false)
const autoRotate = ref(false)

let graphInstance = null
let pollTimer = null
let rotateHandle = null

// Z-plane depths per node type — 3 distinct visual planes
const PLANE_Z = {
  Brand: 0, Person: 0, Influencer: 0,
  Topic: 150,
  Unknown: 300, Source: 300, Event: 300, Community: 300, Product: 300,
}

// Node colors
const NODE_COLOR = {
  Brand: '#6366F1', Person: '#6366F1', Influencer: '#6366F1',
  Topic: '#0EA5E9',
  Unknown: '#10B981', Source: '#10B981', Event: '#10B981',
  Community: '#10B981', Product: '#10B981',
}

function getZ(type) { return PLANE_Z[type] ?? 300 }
function getColor(type) { return NODE_COLOR[type] || '#10B981' }
function getSize(type) {
  if (type === 'Brand') return 8
  if (type === 'Person' || type === 'Influencer') return 5
  return 3
}

function initGraph() {
  if (!containerRef.value) return

  graphInstance = ForceGraph3D({ controlType: 'orbit' })(containerRef.value)
    .backgroundColor('#FAFBFF')
    .showNavInfo(false)
    // Links
    .linkColor(() => 'rgba(180,185,210,0.45)')
    .linkWidth(0.8)
    .linkDirectionalParticles(1)
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleColor(() => 'rgba(99,102,241,0.5)')
    // Nodes
    .nodeColor(d => getColor(d.type))
    .nodeVal(d => getSize(d.type))
    .nodeLabel(d => `
      <div style="
        background:#fff;border:1px solid #E8EAEF;border-radius:8px;
        padding:6px 10px;font-size:12px;color:#111827;
        box-shadow:0 4px 12px rgba(0,0,0,0.1);
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        max-width:200px;line-height:1.4">
        <strong>${d.label || d.id}</strong><br/>
        <span style="color:#6B7280;font-size:10px">${d.type || 'Node'}</span>
      </div>
    `)
    .onEngineStop(() => {
      // After simulation settles, snap nodes closer to their Z plane
      if (!graphInstance) return
      const data = graphInstance.graphData()
      data.nodes.forEach(n => {
        n.z = (n.z || 0) * 0.2 + getZ(n.type) * 0.8
      })
      graphInstance.graphData(data)
    })

  // Custom force: spring each node toward its target Z plane each tick
  graphInstance.d3Force('z-plane', alpha => {
    if (!graphInstance) return
    graphInstance.graphData().nodes.forEach(n => {
      const targetZ = getZ(n.type)
      n.vz = (n.vz || 0) + (targetZ - (n.z || 0)) * 0.06 * alpha
    })
  })

  // Stronger repulsion so nodes spread within their planes
  graphInstance.d3Force('charge')?.strength(-150)

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
      z: getZ(n.type || 'Unknown'), // initial z hint for the force engine
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
  graphInstance?.cameraPosition({ x: 0, y: 0, z: 600 }, { x: 0, y: 0, z: 0 }, 1000)
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
  loadData()
})

onMounted(() => {
  initGraph()
  loadData()
  pollTimer = setInterval(loadData, 10000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(rotateHandle)
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
  height: 600px;
  background: var(--graph-bg);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-md);
}

.graph-container { width: 100%; height: 100%; }

.graph-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.empty-inner {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  color: var(--text-faint); font-size: 13px; text-align: center;
}
.empty-icon { font-size: 36px; color: var(--border-default); }

/* Glass legend bar */
.graph-legend {
  position: absolute; bottom: 14px; left: 14px;
  display: flex; gap: 14px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 7px 14px;
  box-shadow: var(--shadow-sm);
}
.leg-item {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--text-muted); font-weight: 500;
}
.leg-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.leg-plane {
  font-size: 9px; color: var(--text-faint);
  background: var(--bg-overlay); padding: 1px 4px; border-radius: 3px;
}

/* Float control buttons */
.graph-controls {
  position: absolute; top: 14px; right: 14px;
  display: flex; flex-direction: column; gap: 4px;
}
.ctrl-btn {
  width: 30px; height: 30px;
  border: 1px solid var(--border-default);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  cursor: pointer; font-size: 15px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
  transition: background var(--transition-fast), color var(--transition-fast);
  box-shadow: var(--shadow-sm);
}
.ctrl-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.ctrl-btn.active { background: var(--accent-muted); color: var(--accent); border-color: var(--accent); }

/* Stats chip */
.graph-stats {
  position: absolute; top: 14px; left: 14px;
  font-size: 11px; color: var(--text-muted);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  box-shadow: var(--shadow-sm);
}
</style>
