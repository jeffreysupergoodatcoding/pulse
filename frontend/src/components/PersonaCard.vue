<template>
  <div class="persona-card card" :style="{ borderLeft: sentimentBorderStyle }">
    <div class="card-header">
      <div class="arch-meta">
        <div class="arch-name">{{ archetype.archetype_id || 'Archetype' }}</div>
        <div class="arch-count">{{ archetype.size || archetype.n_agents || '?' }} agents</div>
      </div>
      <div class="sentiment-chip" :class="sentimentClass">
        {{ formatScore(archetype.avg_sentiment || archetype.sentiment_score) }}
      </div>
    </div>

    <div v-if="archetype.description" class="arch-desc">{{ archetype.description }}</div>

    <div v-if="traits.length" class="traits">
      <span v-for="t in traits" :key="t" class="trait-pill">{{ t }}</span>
    </div>

    <div v-if="quotes.length" class="quotes">
      <div v-for="(q, i) in quotes.slice(0, 2)" :key="i" class="quote">"{{ q }}"</div>
    </div>

    <div v-if="archetype.dominant_emotion" class="emotion-row">
      <span class="emotion-label">Emotion</span>
      <span class="emotion-badge">{{ archetype.dominant_emotion }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ archetype: { type: Object, required: true } })

const sentimentClass = computed(() => {
  const s = props.archetype.avg_sentiment ?? props.archetype.sentiment_score ?? 0
  if (s > 0.1) return 'pos'
  if (s < -0.1) return 'neg'
  return 'neu'
})

const sentimentBorderStyle = computed(() => {
  const s = props.archetype.avg_sentiment ?? props.archetype.sentiment_score ?? 0
  if (s > 0.1) return '3px solid var(--positive)'
  if (s < -0.1) return '3px solid var(--negative)'
  return '3px solid var(--border-default)'
})

const traits = computed(() => {
  const v = props.archetype.vocabulary || props.archetype.top_terms || []
  return Array.isArray(v) ? v.slice(0, 6) : []
})

const quotes = computed(() => {
  return props.archetype.representative_quotes || props.archetype.sample_quotes || []
})

function formatScore(s) {
  if (s == null) return '–'
  return (s >= 0 ? '+' : '') + Number(s).toFixed(2)
}
</script>

<style scoped>
.persona-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: box-shadow var(--transition-base), transform var(--transition-base);
}
.persona-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.arch-meta { flex: 1; min-width: 0; }

.arch-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.arch-count {
  font-size: 11px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  margin-top: 1px;
}

.sentiment-chip {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: -0.3px;
  flex-shrink: 0;
  font-family: var(--font-sans);
}
.sentiment-chip.pos { color: var(--positive); }
.sentiment-chip.neg { color: var(--negative); }
.sentiment-chip.neu { color: var(--text-muted); }

.arch-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.55;
}

.traits {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.trait-pill {
  padding: 2px 7px;
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.quotes {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.quote {
  font-size: 11px;
  color: var(--text-muted);
  font-style: normal;
  padding: 7px 10px;
  background: var(--bg-canvas);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--border-default);
  line-height: 1.55;
}

.emotion-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.emotion-label {
  color: var(--text-faint);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-weight: 600;
}
.emotion-badge {
  padding: 2px 8px;
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: -0.1px;
}
</style>
