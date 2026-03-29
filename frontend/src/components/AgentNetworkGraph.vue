<template>
  <div class="ang-wrap" ref="wrapRef">
    <!-- ForceGraph3D mounts into this dedicated div — Vue does NOT manage its children -->
    <div class="ang-graph-container" ref="graphContainerRef"></div>

    <!-- Vue-managed overlays (all absolutely positioned, won't conflict with ForceGraph3D) -->
    <div class="ang-dot-grid" />

    <div class="ang-toolbar">
      <button class="ang-btn" @click="resetView" title="Re-center">⌖</button>
      <button class="ang-btn" :class="{ active: autoRotate }" @click="toggleRotate" title="Auto-rotate">↻</button>
      <button class="ang-btn" @click="fitView" title="Fit to screen">⤢</button>
    </div>

    <div class="ang-popup" :class="{ visible: !!selected }">
      <button class="ang-popup-close" @click="selected = null" aria-label="Close">×</button>
      <div v-if="selected">
        <div class="ang-popup-title">Agent Details</div>
        <div class="ang-popup-row"><span>Agent ID</span><span>@{{ selected.label }}</span></div>
        <div class="ang-popup-row"><span>Type</span><span>{{ selected.archetype || 'Agent' }}</span></div>
        <div class="ang-popup-row">
          <span>Sentiment</span>
          <span :style="{ color: sentimentColor(selected.sentiment) }">{{ sentimentLabel(selected.sentiment) }}</span>
        </div>
        <div class="ang-popup-row"><span>Actions</span><span>{{ selected.activityCount }}</span></div>
        <div class="ang-popup-row" v-if="selected.lastAction">
          <span>Last action</span><span>{{ selected.lastAction }}</span>
        </div>
      </div>
    </div>

    <div class="ang-legend">
      <div v-for="(color, label) in legendItems" :key="label" class="ang-leg-item">
        <span class="ang-leg-dot" :style="{ background: color }" />
        <span>{{ label }}</span>
      </div>
    </div>

    <div v-if="nodeCount === 0" class="ang-empty">
      Agent network will appear here once the simulation starts
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import ForceGraph3D from '3d-force-graph'

const props = defineProps({
  simId:   { type: String, required: true },
  actions: { type: Array,  default: () => [] },
  running: { type: Boolean, default: false },
})

const wrapRef           = ref(null)
const graphContainerRef = ref(null)
const selected   = ref(null)
const nodeCount  = ref(0)
const autoRotate = ref(false)

let graphInstance  = null
let resizeObserver = null
let rotateHandle   = null
let initialized    = false

// Accumulated node/edge state
let nodeMap = new Map()
let edgeMap = new Map()

const COLORS = {
  positive:    '#22C55E',
  negative:    '#EF4444',
  neutral:     '#EAB308',
  media:       '#3B82F6',
  institution: '#8B5CF6',
}

const legendItems = {
  'Positive':    COLORS.positive,
  'Negative':    COLORS.negative,
  'Neutral':     COLORS.neutral,
  'Media':       COLORS.media,
  'Institution': COLORS.institution,
}

function nodeColor(node) {
  const arch = (node.archetype || '').toLowerCase()
  if (arch.includes('media') || arch.includes('outlet')) return COLORS.media
  if (arch.includes('institution') || arch.includes('investor') || arch.includes('gov')) return COLORS.institution
  const s = node.sentiment || 0
  if (s > 0.15)  return COLORS.positive
  if (s < -0.15) return COLORS.negative
  return COLORS.neutral
}

function nodeVal(node) {
  return 2 + Math.min((node.activityCount || 0) * 0.6, 8)
}

function edgeColor(type) {
  const map = {
    like_post:      COLORS.positive,
    create_post:    '#6366F1',
    create_comment: '#0EA5E9',
    repost:         '#8B5CF6',
    follow:         '#F59E0B',
    dislike_post:   COLORS.negative,
  }
  return map[type] || 'rgba(150,158,180,0.5)'
}

function sentimentColor(s) {
  if (s > 0.15) return '#059669'
  if (s < -0.15) return '#DC2626'
  return '#6B7280'
}
function sentimentLabel(s) {
  if (s > 0.5)   return 'Highly Positive'
  if (s > 0.15)  return 'Positive'
  if (s < -0.5)  return 'Highly Negative'
  if (s < -0.15) return 'Negative'
  return 'Neutral'
}

function buildGraphData(actions) {
  for (const action of actions) {
    const agentId = action.agent_id || action.user_id
    if (!agentId) continue

    if (!nodeMap.has(agentId)) {
      nodeMap.set(agentId, {
        id: agentId,
        label: agentId.slice(0, 8),
        archetype: action.archetype_id || action.persona_type || '',
        sentiment: action.sentiment_score || 0,
        activityCount: 0,
        lastAction: '',
      })
    }
    const n = nodeMap.get(agentId)
    n.activityCount++
    n.lastAction = action.action_type || ''
    n.sentiment  = n.sentiment * 0.7 + (action.sentiment_score || 0) * 0.3

    const targetId = action.target_agent_id || action.parent_agent_id
    if (targetId && targetId !== agentId) {
      const key = `${agentId}→${targetId}`
      if (!edgeMap.has(key)) {
        edgeMap.set(key, { source: agentId, target: targetId, type: action.action_type, count: 0 })
      }
      edgeMap.get(key).count++
    }
  }
}

function pushToGraph() {
  if (!graphInstance) return
  const gNodes = [...nodeMap.values()].map(n => ({ ...n }))
  const gLinks = [...edgeMap.values()].map(e => ({
    source: e.source,
    target: e.target,
    type:   e.type,
    width:  Math.min(0.4 + e.count * 0.3, 3),
  }))
  nodeCount.value = gNodes.length
  graphInstance.graphData({ nodes: gNodes, links: gLinks })
}

function initGraph(w, h) {
  if (graphInstance || !graphContainerRef.value) return
  initialized = true

  graphInstance = ForceGraph3D({ controlType: 'orbit' })(graphContainerRef.value)
    .width(w)
    .height(h)
    .backgroundColor('rgba(0,0,0,0)')
    .showNavInfo(false)
    .nodeColor(d => nodeColor(d))
    .nodeVal(d => nodeVal(d))
    .nodeLabel(d => `
      <div style="
        background:#fff;border:1px solid #E2E6EF;border-radius:10px;
        padding:8px 12px;font-size:12px;color:#111827;
        box-shadow:0 4px 16px rgba(15,23,42,0.10);
        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
        max-width:200px;line-height:1.5">
        <strong>@${d.label}</strong><br/>
        <span style="color:#9CA3AF;font-size:10px;text-transform:uppercase;letter-spacing:0.5px">
          ${d.archetype || 'Agent'} · ${sentimentLabel(d.sentiment)}
        </span>
      </div>
    `)
    .onNodeClick(node => { selected.value = node })
    .linkColor(l => edgeColor(l.type))
    .linkWidth(l => l.width || 0.5)
    .linkDirectionalParticles(1)
    .linkDirectionalParticleWidth(1.2)
    .linkDirectionalParticleColor(l => edgeColor(l.type))
    .onEngineStop(() => {
      if (!graphInstance || nodeCount.value === 0) return
      graphInstance.zoomToFit(800, 80)
    })

  graphInstance.d3Force('z-plane', null)
  graphInstance.d3Force('charge')?.strength(-100)
  graphInstance.d3Force('link')?.distance(40).strength(0.7)
}

watch(() => props.actions, (newActions) => {
  if (!newActions?.length) return
  buildGraphData(newActions)
  pushToGraph()
}, { deep: false })

function resetView() { graphInstance?.zoomToFit(800, 80) }
function fitView()   { graphInstance?.zoomToFit(400, 40) }

function toggleRotate() {
  autoRotate.value = !autoRotate.value
  if (autoRotate.value) {
    let angle = 0
    rotateHandle = setInterval(() => {
      angle += 0.004
      graphInstance?.cameraPosition({
        x: 400 * Math.sin(angle),
        y: 0,
        z: 400 * Math.cos(angle),
      })
    }, 16)
  } else {
    clearInterval(rotateHandle)
  }
}

onMounted(() => {
  if (!graphContainerRef.value) return

  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0) {
        if (!initialized) {
          initGraph(width, height)
          if (props.actions?.length) {
            buildGraphData(props.actions)
            pushToGraph()
          }
        } else if (graphInstance) {
          graphInstance.width(width).height(height)
        }
      }
    }
  })
  resizeObserver.observe(graphContainerRef.value)
})

onUnmounted(() => {
  clearInterval(rotateHandle)
  resizeObserver?.disconnect()
  if (graphInstance) {
    // Stop animation and dispose resources — do NOT manually remove DOM nodes,
    // Vue will handle removing the parent element and all its children.
    try { graphInstance.pauseAnimation() } catch { /* ignore */ }
    try { graphInstance.controls()?.dispose() } catch { /* ignore */ }
    try { graphInstance.renderer()?.dispose() } catch { /* ignore */ }
    try { graphInstance._destructor?.() } catch { /* ignore */ }
    graphInstance = null
  }
  initialized = false
  nodeMap = new Map()
  edgeMap = new Map()
})
</script>

<style scoped>
.ang-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  background: #FFFFFF;
  overflow: hidden;
}

/* Dedicated container for ForceGraph3D — Vue treats this as an opaque leaf node */
.ang-graph-container {
  position: absolute;
  inset: 0;
  z-index: 0;
}

/* Dot-grid — sits ABOVE the 3D canvas using z-index */
.ang-dot-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(0,0,0,0.09) 1px, transparent 1px);
  background-size: 22px 22px;
  pointer-events: none;
  z-index: 1;
}

/* Toolbar */
.ang-toolbar {
  position: absolute;
  top: 12px;
  right: 14px;
  display: flex;
  gap: 4px;
  z-index: 10;
}
.ang-btn {
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
}
.ang-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-strong); }
.ang-btn.active { background: var(--text-primary); color: #FFFFFF; border-color: var(--text-primary); }

/* Interaction popup */
.ang-popup {
  position: absolute; top: 54px; right: 14px;
  width: 260px;
  background: rgba(255,255,255,0.98);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 16px; box-shadow: var(--shadow-lg);
  transform: translateX(280px); opacity: 0;
  transition: transform var(--transition-base), opacity var(--transition-base);
  z-index: 20;
}
.ang-popup.visible { transform: translateX(0); opacity: 1; }
.ang-popup-close {
  position: absolute; top: 10px; right: 12px;
  background: none; border: none; cursor: pointer;
  font-size: 18px; color: var(--text-faint); line-height: 1;
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
}
.ang-popup-close:hover { color: var(--text-primary); }
.ang-popup-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.8px; color: var(--text-primary); margin-bottom: 10px;
}
.ang-popup-row {
  display: flex; justify-content: space-between;
  font-size: 12px; padding: 5px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.ang-popup-row:last-child { border-bottom: none; padding-bottom: 0; }
.ang-popup-row > span:first-child { color: var(--text-faint); }
.ang-popup-row > span:last-child  { color: var(--text-primary); font-weight: 500; text-align: right; max-width: 160px; }

/* Legend */
.ang-legend {
  position: absolute; bottom: 12px; left: 14px;
  display: flex; flex-wrap: wrap; gap: 5px; z-index: 10;
}
.ang-leg-item {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 9px; font-size: 10px;
  color: var(--text-muted); font-weight: 500;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-sm);
  font-family: var(--font-sans); letter-spacing: -0.1px;
}
.ang-leg-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

/* Empty state */
.ang-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-faint); font-size: 13px;
  pointer-events: none; z-index: 15;
}
</style>
