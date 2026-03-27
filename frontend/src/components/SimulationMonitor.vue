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
.monitor { background: #0d1117; border: 1px solid #2d3748; border-radius: 8px; overflow: hidden; }
.monitor-header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-bottom: 1px solid #2d3748;
  background: #161b27;
}
.round-badge { font-size: 13px; color: #94a3b8; }
.status-pill { padding: 2px 10px; border-radius: 9999px; font-size: 11px; font-weight: 600; }
.pill-running { background: #1e3a5f; color: #60a5fa; }
.pill-done    { background: #14532d; color: #4ade80; }
.pill-error   { background: #450a0a; color: #f87171; }
.pill-idle    { background: #1e2433; color: #64748b; }

.action-feed { max-height: 400px; overflow-y: auto; }
.action-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; font-size: 12px; border-bottom: 1px solid #1a1f2e;
}
.action-row.pos { border-left: 2px solid #16a34a; }
.action-row.neg { border-left: 2px solid #dc2626; }
.action-row.neu { border-left: 2px solid transparent; }
.action-row:hover { background: #161b27; }

.action-round   { color: #4b5563; width: 28px; flex-shrink: 0; }
.action-badge   { padding: 1px 6px; border-radius: 4px; background: #1e2433; color: #94a3b8; flex-shrink: 0; }
.at-like_post   { background: #14532d33; color: #4ade80; }
.at-dislike_post{ background: #450a0a33; color: #f87171; }
.at-create_post { background: #1e3a5f33; color: #60a5fa; }
.at-create_comment { background: #2d1b6933; color: #c084fc; }
.at-repost      { background: #1c3d2a33; color: #34d399; }
.at-follow      { background: #1e283833; color: #94a3b8; }
.action-agent   { color: #64748b; width: 70px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-platform{ color: #4b5563; width: 50px; flex-shrink: 0; }
.action-content { flex: 1; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-score   { flex-shrink: 0; font-weight: 600; font-size: 11px; }
.action-score.pos { color: #4ade80; }
.action-score.neg { color: #f87171; }
.action-score.neu { color: #64748b; }
</style>
