<template>
  <div class="chart-wrap">
    <canvas ref="canvasRef" />
    <div v-if="!hasData" class="chart-empty">No sentiment data yet.</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

const props = defineProps({
  sentimentByRound: { type: Array, default: () => [] },
  byArchetype: { type: Object, default: () => ({}) },
  trajectory: { type: Object, default: () => ({}) },
})

const canvasRef = ref(null)
const hasData = ref(false)
let chartInstance = null

const ARCH_COLORS = ['#7c3aed','#2563eb','#0891b2','#16a34a','#d97706','#dc2626','#db2777','#9333ea']

function buildChart() {
  if (!canvasRef.value) return
  const rounds = props.sentimentByRound
  hasData.value = rounds.length > 0
  if (!hasData.value) return

  const labels = rounds.map(r => `R${r.round}`)
  const overallData = rounds.map(r => r.mean_score)

  const datasets = [{
    label: 'Overall',
    data: overallData,
    borderColor: '#7c3aed',
    backgroundColor: 'rgba(124,58,237,0.1)',
    borderWidth: 2,
    tension: 0.3,
    fill: true,
    pointRadius: 2,
  }]

  // Add trajectory forecast line
  const traj = props.trajectory
  if (traj?.predicted_final_score != null && rounds.length > 2) {
    const firstScore = rounds[0]?.mean_score ?? 0
    const lastRound = rounds[rounds.length - 1]?.round ?? rounds.length
    const forecastLabels = [`R${lastRound}+1`]
    datasets.push({
      label: 'Forecast',
      data: [...Array(rounds.length - 1).fill(null), overallData[overallData.length - 1], traj.predicted_final_score],
      borderColor: '#f59e0b',
      borderWidth: 1,
      borderDash: [4, 4],
      pointRadius: 3,
      fill: false,
      tension: 0.2,
    })
  }

  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(canvasRef.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
        tooltip: { backgroundColor: '#1e2433', titleColor: '#e2e8f0', bodyColor: '#94a3b8' },
      },
      scales: {
        x: { ticks: { color: '#4b5563', font: { size: 10 } }, grid: { color: '#1e2433' } },
        y: {
          min: -1, max: 1,
          ticks: { color: '#4b5563', font: { size: 10 } },
          grid: { color: '#1e2433' },
        },
      },
    },
  })
}

watch(() => props.sentimentByRound, buildChart, { deep: true })
onMounted(buildChart)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>

<style scoped>
.chart-wrap { position: relative; height: 260px; }
.chart-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #4b5563; font-size: 13px; }
</style>
