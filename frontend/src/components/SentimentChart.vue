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

const ARCH_COLORS = ['#6366F1','#0EA5E9','#10B981','#F59E0B','#EF4444','#8B5CF6','#EC4899','#14B8A6']

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
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99,102,241,0.08)',
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
      borderColor: '#D97706',
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
        legend: { labels: { color: '#6B7280', font: { size: 11 } } },
        tooltip: {
          backgroundColor: '#FFFFFF', titleColor: '#111827', bodyColor: '#6B7280',
          borderColor: '#E8EAEF', borderWidth: 1,
        },
      },
      scales: {
        x: { ticks: { color: '#6B7280', font: { size: 10 } }, grid: { color: '#F1F3F7' } },
        y: {
          min: -1, max: 1,
          ticks: { color: '#6B7280', font: { size: 10 } },
          grid: { color: '#F1F3F7' },
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
.chart-wrap { position: relative; height: 260px; background: var(--bg-raised); border-radius: var(--radius-md); }
.chart-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: 13px; }
</style>
