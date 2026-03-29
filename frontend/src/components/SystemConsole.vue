<template>
  <div class="sys-console">
    <div class="sys-header">
      <span class="sys-title">SYSTEM DASHBOARD</span>
      <span class="sys-sim-id" v-if="simId">{{ simId }}</span>
      <span class="sys-status" v-if="status.status">
        <span class="sys-dot" :class="status.status" />
        {{ (status.status || '').toUpperCase() }}
      </span>
    </div>
    <div class="sys-body" ref="bodyRef">
      <div
        v-for="(log, i) in displayLogs"
        :key="i"
        class="sys-line"
      >
        <span class="sys-time">{{ log.time }}</span>
        <span class="sys-icon" :class="log.type">{{ log.icon }}</span>
        <span class="sys-msg">{{ log.message }}</span>
      </div>
      <div v-if="!displayLogs.length" class="sys-empty">
        Waiting for simulation output…
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'

const props = defineProps({
  simId:   { type: String, default: '' },
  actions: { type: Array,  default: () => [] },
  status:  { type: Object, default: () => ({}) },
})

const bodyRef = ref(null)
const logs = ref([])
const seenActionIds = new Set()

function formatTime(d) {
  return d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

function actionToLog(action) {
  const agent = action.agent_id || action.user_id || 'unknown'
  const type  = action.action_type || 'action'
  const sentiment = action.sentiment_score
  let icon = '→'
  let msgType = 'info'

  if (type.includes('post')) { icon = '✦'; msgType = 'post' }
  else if (type.includes('comment')) { icon = '◆'; msgType = 'comment' }
  else if (type.includes('like')) { icon = '✓'; msgType = 'positive' }
  else if (type.includes('dislike')) { icon = '✕'; msgType = 'negative' }
  else if (type.includes('repost') || type.includes('share')) { icon = '↻'; msgType = 'share' }
  else if (type.includes('follow')) { icon = '+'; msgType = 'follow' }

  let sentimentStr = ''
  if (sentiment != null) {
    sentimentStr = ` [score: ${sentiment >= 0 ? '+' : ''}${sentiment.toFixed(2)}]`
  }

  return {
    time: formatTime(new Date()),
    icon,
    type: msgType,
    message: `@${agent} ${type.replace(/_/g, ' ')}${sentimentStr}`,
  }
}

watch(() => props.status, (newStatus, oldStatus) => {
  if (!oldStatus?.status && newStatus?.status === 'running') {
    logs.value.push({
      time: formatTime(new Date()),
      icon: '▶',
      type: 'start',
      message: `Simulation started · ${props.simId || ''}`,
    })
  }
  if (newStatus?.current_round && newStatus.current_round !== oldStatus?.current_round) {
    logs.value.push({
      time: formatTime(new Date()),
      icon: '←',
      type: 'round',
      message: `Round ${newStatus.current_round} of ${newStatus.total_rounds || '?'} started`,
    })
    scrollToBottom()
  }
  if (newStatus?.status === 'completed' && oldStatus?.status !== 'completed') {
    logs.value.push({
      time: formatTime(new Date()),
      icon: '✓',
      type: 'done',
      message: `Simulation completed · ${newStatus.actions_count || 0} actions logged`,
    })
    scrollToBottom()
  }
}, { deep: true })

watch(() => props.actions, (newActions) => {
  let added = false
  for (const action of newActions.slice(-20)) {
    const id = action.action_id || `${action.agent_id}:${action.round}:${action.action_type}`
    if (seenActionIds.has(id)) continue
    seenActionIds.add(id)
    logs.value.push(actionToLog(action))
    added = true
  }
  // Keep last 200 log lines
  if (logs.value.length > 200) logs.value = logs.value.slice(-200)
  if (added) scrollToBottom()
}, { deep: false })

async function scrollToBottom() {
  await nextTick()
  if (bodyRef.value) {
    bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  }
}

const displayLogs = computed(() => logs.value)
</script>

<style scoped>
.sys-console {
  height: 120px;
  flex-shrink: 0;
  background: #0D1117;
  border-top: 1px solid #21262D;
  font-family: var(--font-mono);
  font-size: 11px;
  display: flex;
  flex-direction: column;
}

.sys-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 5px 14px;
  border-bottom: 1px solid #21262D;
  flex-shrink: 0;
}
.sys-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #58A6FF;
}
.sys-sim-id {
  font-size: 10px;
  color: #484F58;
  letter-spacing: 0.5px;
}
.sys-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: #8B949E;
  margin-left: auto;
  letter-spacing: 0.5px;
}
.sys-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #8B949E;
}
.sys-dot.running { background: #3FB950; }
.sys-dot.completed { background: #58A6FF; }
.sys-dot.error { background: #F85149; }

.sys-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 14px 6px;
  scroll-behavior: smooth;
}
.sys-body::-webkit-scrollbar { width: 4px; }
.sys-body::-webkit-scrollbar-track { background: transparent; }
.sys-body::-webkit-scrollbar-thumb { background: #30363D; border-radius: 2px; }

.sys-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 1px 0;
  color: #8B949E;
  line-height: 1.5;
}

.sys-time {
  color: #30363D;
  white-space: nowrap;
  flex-shrink: 0;
  font-size: 10px;
}

.sys-icon {
  flex-shrink: 0;
  width: 10px;
  text-align: center;
  color: #3FB950;
}
.sys-icon.negative { color: #F85149; }
.sys-icon.round    { color: #58A6FF; }
.sys-icon.start    { color: #3FB950; }
.sys-icon.done     { color: #A5D6FF; }
.sys-icon.post     { color: #D2A8FF; }
.sys-icon.comment  { color: #79C0FF; }
.sys-icon.share    { color: #FFA657; }
.sys-icon.follow   { color: #56D364; }

.sys-msg {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
}

.sys-empty {
  color: #30363D;
  font-size: 11px;
  padding: 8px 0;
  font-style: italic;
}
</style>
