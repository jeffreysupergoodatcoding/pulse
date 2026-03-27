<template>
  <div class="persona-card card">
    <div class="card-header">
      <div>
        <div class="arch-name">{{ archetype.archetype_id || 'Archetype' }}</div>
        <div class="arch-count">{{ archetype.size || archetype.n_agents || '?' }} agents</div>
      </div>
      <div class="sentiment-indicator" :class="sentimentClass">
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
      <span class="text-muted">Dominant emotion:</span>
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
.persona-card { display: flex; flex-direction: column; gap: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: flex-start; }
.arch-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.arch-count { font-size: 12px; color: var(--text-faint); }
.sentiment-indicator { font-size: 16px; font-weight: 700; }
.sentiment-indicator.pos { color: var(--positive); }
.sentiment-indicator.neg { color: var(--negative); }
.sentiment-indicator.neu { color: var(--text-muted); }
.arch-desc { font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.traits { display: flex; flex-wrap: wrap; gap: 4px; }
.trait-pill {
  padding: 2px 8px;
  background: var(--bg-overlay);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  font-size: 11px; color: var(--text-muted);
}
.quotes { display: flex; flex-direction: column; gap: 4px; }
.quote {
  font-size: 12px; color: var(--text-muted); font-style: italic;
  padding: 6px 10px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--accent);
}
.emotion-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.emotion-badge {
  padding: 2px 8px;
  background: var(--accent-light);
  color: var(--accent);
  border-radius: var(--radius-full);
  font-size: 11px;
}
</style>
