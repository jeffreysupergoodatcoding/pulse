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
.arch-name { font-weight: 600; font-size: 14px; color: #f1f5f9; }
.arch-count { font-size: 12px; color: #64748b; }
.sentiment-indicator { font-size: 16px; font-weight: 700; }
.sentiment-indicator.pos { color: #4ade80; }
.sentiment-indicator.neg { color: #f87171; }
.sentiment-indicator.neu { color: #94a3b8; }
.arch-desc { font-size: 12px; color: #94a3b8; line-height: 1.5; }
.traits { display: flex; flex-wrap: wrap; gap: 4px; }
.trait-pill { padding: 2px 8px; background: #1e2433; border-radius: 9999px; font-size: 11px; color: #94a3b8; }
.quotes { display: flex; flex-direction: column; gap: 4px; }
.quote { font-size: 12px; color: #64748b; font-style: italic; padding: 6px 10px; background: #0d1117; border-radius: 4px; border-left: 2px solid #374151; }
.emotion-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.emotion-badge { padding: 2px 8px; background: #2d1b69; color: #c084fc; border-radius: 9999px; font-size: 11px; }
</style>
