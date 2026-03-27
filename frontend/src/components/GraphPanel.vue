<template>
  <div class="graph-wrap">
    <div v-if="!nodes.length" class="graph-empty">
      No graph data. Run <strong>Build Graph</strong> first.
    </div>
    <svg ref="svgRef" class="graph-svg" />
    <div class="graph-legend">
      <span class="leg-item"><span class="leg-dot brand" />Entity</span>
      <span class="leg-item"><span class="leg-dot topic" />Topic</span>
      <span class="leg-item"><span class="leg-dot other" />Other</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as d3 from 'd3'
import { graph as graphApi } from '../api/graph.js'

const props = defineProps({ entityId: String })
const svgRef = ref(null)
const nodes = ref([])
const edges = ref([])
let timer = null
let simulation = null

const COLOR = { Brand: '#7c3aed', Person: '#2563eb', Topic: '#0891b2', Unknown: '#475569' }

async function fetchData() {
  if (!props.entityId) return
  try {
    const r = await graphApi.getData(props.entityId)
    nodes.value = r.data.nodes || []
    edges.value = r.data.edges || []
    render()
  } catch { /* ignore */ }
}

function render() {
  const svg = d3.select(svgRef.value)
  svg.selectAll('*').remove()
  if (!nodes.value.length) return

  const el = svgRef.value
  const W = el.clientWidth || 700
  const H = el.clientHeight || 500

  svg.attr('width', W).attr('height', H)

  const nodeMap = {}
  const sim_nodes = nodes.value.map(n => {
    const obj = { ...n, id: n.id }
    nodeMap[n.id] = obj
    return obj
  })
  const sim_links = edges.value
    .filter(e => nodeMap[e.source] && nodeMap[e.target])
    .map(e => ({ ...e, source: e.source, target: e.target }))

  simulation = d3.forceSimulation(sim_nodes)
    .force('link', d3.forceLink(sim_links).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(20))

  const g = svg.append('g')

  svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => g.attr('transform', e.transform)))

  const link = g.append('g').selectAll('line').data(sim_links).join('line')
    .attr('stroke', '#374151').attr('stroke-width', 1).attr('stroke-opacity', 0.6)

  const node = g.append('g').selectAll('circle').data(sim_nodes).join('circle')
    .attr('r', d => d.type === 'Brand' ? 14 : 8)
    .attr('fill', d => COLOR[d.type] || COLOR.Unknown)
    .attr('stroke', '#0f1117').attr('stroke-width', 2)
    .call(d3.drag()
      .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
    )

  const label = g.append('g').selectAll('text').data(sim_nodes).join('text')
    .text(d => d.label)
    .attr('font-size', 10).attr('fill', '#94a3b8').attr('text-anchor', 'middle').attr('dy', 22)

  const linkLabel = g.append('g').selectAll('text').data(sim_links).join('text')
    .text(d => d.label || d.relation || '')
    .attr('font-size', 9).attr('fill', '#4b5563').attr('text-anchor', 'middle')

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
    node.attr('cx', d => d.x).attr('cy', d => d.y)
    label.attr('x', d => d.x).attr('y', d => d.y)
    linkLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2)
  })
}

watch(() => props.entityId, fetchData)
onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, 5000)
})
onUnmounted(() => {
  clearInterval(timer)
  if (simulation) simulation.stop()
})
</script>

<style scoped>
.graph-wrap { position: relative; width: 100%; height: 500px; background: #0d1117; border-radius: 8px; border: 1px solid #2d3748; overflow: hidden; }
.graph-svg { width: 100%; height: 100%; }
.graph-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #4b5563; font-size: 14px; }
.graph-legend { position: absolute; bottom: 12px; left: 12px; display: flex; gap: 12px; }
.leg-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #64748b; }
.leg-dot { width: 8px; height: 8px; border-radius: 50%; }
.brand { background: #7c3aed; }
.topic { background: #0891b2; }
.other { background: #475569; }
</style>
