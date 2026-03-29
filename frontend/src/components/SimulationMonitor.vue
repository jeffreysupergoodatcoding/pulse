<template>
  <div class="monitor">
    <div class="action-feed" ref="feedRef">
      <div v-if="!actions.length" class="feed-empty">
        Waiting for agent actions…
      </div>
      <div
        v-for="(action, i) in actions"
        :key="i"
        class="action-row"
        :class="sentimentClass(action.sentiment_score)"
      >
        <div class="action-main">
          <div class="action-header">
            <span class="action-type-label">{{ agentType(action) }}</span>
            <span class="action-sentiment" :class="sentimentClass(action.sentiment_score)" v-if="action.sentiment_score != null">
              [Sentiment: {{ sentimentLabel(action.sentiment_score) }}]
            </span>
            <span class="action-agent-right">{{ action.agent_id }}</span>
          </div>
          <div class="action-content" v-if="actionContent(action)">
            {{ truncate(actionContent(action), 120) }}
          </div>
          <div class="action-meta">
            <span class="action-badge" :class="`at-${action.action_type}`">{{ action.action_type?.replace(/_/g, ' ') }}</span>
            <span class="action-round">R{{ action.round }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  actions: { type: Array, default: () => [] },
  status:  { type: Object, default: () => ({}) },
})

const feedRef = ref(null)

function sentimentClass(score) {
  if (score == null) return ''
  if (score > 0.2) return 'pos'
  if (score < -0.2) return 'neg'
  return 'neu'
}

function sentimentLabel(score) {
  if (score > 0.3) return 'Positive'
  if (score < -0.3) return 'Negative'
  return 'Neutral'
}

function agentType(action) {
  if (action.archetype_id) return action.archetype_id.toUpperCase().slice(0, 16)
  return 'AGENT'
}

function actionContent(action) {
  return action.action_args?.content || action.content || ''
}

function truncate(s, n = 120) {
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
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.action-feed {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-canvas);
}
.action-feed::-webkit-scrollbar { width: 4px; }
.action-feed::-webkit-scrollbar-thumb { background: var(--border-default); border-radius: 2px; }

.feed-empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-faint);
  font-size: 12px;
}

.action-row {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  border-left: 3px solid transparent;
  transition: background var(--transition-fast);
}
.action-row:hover { background: var(--bg-hover); }
.action-row.pos { border-left-color: var(--positive); }
.action-row.neg { border-left-color: var(--negative); }

.action-main { display: flex; flex-direction: column; gap: 4px; }

.action-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.action-type-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--text-faint);
}

.action-sentiment {
  font-size: 11px;
  font-weight: 600;
}
.action-sentiment.pos { color: var(--positive); }
.action-sentiment.neg { color: var(--negative); }
.action-sentiment.neu { color: var(--text-muted); }

.action-agent-right {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-content {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.action-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.action-badge {
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--bg-overlay);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 500;
}
.at-like_post      { background: #ECFDF5; color: #065F46; }
.at-dislike_post   { background: var(--negative-bg); color: var(--negative-text); }
.at-create_post    { background: #EFF6FF; color: #1D4ED8; }
.at-create_comment { background: var(--accent-light); color: var(--accent); }
.at-repost         { background: #F0FDF4; color: #166534; }
.at-follow         { background: var(--neutral-bg); color: var(--neutral-text); }

.action-round {
  font-size: 10px;
  color: var(--text-faint);
  font-family: var(--font-mono);
}
.action-platform {
  font-size: 10px;
  color: var(--text-faint);
}
</style>
