<template>
  <div class="monitor">
    <div class="monitor-header">
      <div class="round-badge">Round <strong>{{ status.current_round || 0 }}</strong> / {{ status.total_rounds || '?' }}</div>
      <span class="status-pill" :class="statusClass">{{ status.status || 'idle' }}</span>
      <span class="text-muted" style="font-size:12px">{{ status.actions_count || 0 }} actions</span>
    </div>

    <div class="action-feed" ref="feedRef">
      <div v-if="!actions.length" class="text-muted" style="padding:16px;text-align:center;font-size:13px">
        Waiting for actions…
      </div>
      <div
        v-for="(action, i) in actions"
        :key="i"
        class="action-row"
        :class="sentimentClass(action.sentiment_score)"
      >
        <span class="action-round">R{{ action.round }}</span>
        <span class="action-badge" :class="`at-${action.action_type}`">{{ action.action_type }}</span>
        <span class="action-agent">{{ action.agent_id }}</span>
        <span class="action-platform">{{ action.platform }}</span>
        <span class="action-content">{{ truncate(actionContent(action)) }}</span>
        <span v-if="action.sentiment_score != null" class="action-score" :class="sentimentClass(action.sentiment_score)">
          {{ action.sentiment_score > 0 ? '+' : '' }}{{ action.sentiment_score?.toFixed(2) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  actions: { type: Array, default: () => [] },
  status: { type: Object, default: () => ({}) },
})

const feedRef = ref(null)

const statusClass = computed(() => ({
  'pill-running': props.status.status === 'running',
  'pill-done': props.status.status === 'completed',
  'pill-error': props.status.status === 'error',
  'pill-idle': !props.status.status || props.status.status === 'idle',
}))

function sentimentClass(score) {
  if (score == null) return ''
  if (score > 0.2) return 'pos'
  if (score < -0.2) return 'neg'
  return 'neu'
}

function actionContent(action) {
  return action.action_args?.content || action.content || ''
}

function truncate(s, n = 80) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

watch(() => props.actions.length, async () => {
  await nextTick()
  if (feedRef.value) feedRef.value.scrollTop = feedRef.value.scrollHeight
})
</script>

<style scoped>
.monitor {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.monitor-header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.round-badge { font-size: 13px; color: var(--text-muted); }
.status-pill { padding: 2px 10px; border-radius: var(--radius-full); font-size: 11px; font-weight: 600; }
.pill-running { background: #EFF6FF; color: #1D4ED8; }
.pill-done    { background: var(--positive-bg); color: var(--positive-text); }
.pill-error   { background: var(--negative-bg); color: var(--negative-text); }
.pill-idle    { background: var(--neutral-bg); color: var(--neutral-text); }

.action-feed { max-height: 400px; overflow-y: auto; background: var(--bg-canvas); }
.action-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; font-size: 12px;
  border-bottom: 1px solid var(--border-subtle);
  border-left: 2px solid transparent;
  transition: background var(--transition-fast);
}
.action-row.pos { border-left-color: var(--positive); }
.action-row.neg { border-left-color: var(--negative); }
.action-row:hover { background: var(--bg-hover); }

.action-round    { color: var(--text-faint); width: 28px; flex-shrink: 0; }
.action-badge    { padding: 1px 6px; border-radius: var(--radius-sm); background: var(--bg-overlay); color: var(--text-muted); flex-shrink: 0; }
.at-like_post    { background: #ECFDF5; color: #065F46; }
.at-dislike_post { background: var(--negative-bg); color: var(--negative-text); }
.at-create_post  { background: #EFF6FF; color: #1D4ED8; }
.at-create_comment { background: var(--accent-light); color: var(--accent); }
.at-repost       { background: #F0FDF4; color: #166534; }
.at-follow       { background: var(--neutral-bg); color: var(--neutral-text); }
.action-agent    { color: var(--text-faint); width: 70px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-platform { color: var(--text-faint); width: 50px; flex-shrink: 0; }
.action-content  { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-score    { flex-shrink: 0; font-weight: 600; font-size: 11px; }
.action-score.pos { color: var(--positive); }
.action-score.neg { color: var(--negative); }
.action-score.neu { color: var(--text-muted); }
</style>
