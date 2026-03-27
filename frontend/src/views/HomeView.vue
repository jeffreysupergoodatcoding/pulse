<template>
  <div>
    <div class="section-title">Tracked Entities</div>

    <!-- Add entity form -->
    <div class="card" style="max-width:560px;margin-bottom:24px">
      <div style="font-size:14px;font-weight:600;margin-bottom:14px;color:#f1f5f9">Add Entity</div>
      <div class="grid-2">
        <div>
          <label>Name</label>
          <input v-model="form.name" placeholder="Nike, Taylor Swift…" />
        </div>
        <div>
          <label>Type</label>
          <select v-model="form.entity_type">
            <option value="brand">Brand</option>
            <option value="person">Person</option>
            <option value="influencer">Influencer</option>
          </select>
        </div>
      </div>
      <div class="mt-3">
        <label>Description</label>
        <input v-model="form.description" placeholder="Brief description…" />
      </div>
      <div class="mt-3">
        <label>Keywords (comma-separated)</label>
        <input v-model="form.keywords_raw" placeholder="nike, air max, sneakers" />
      </div>

      <div style="font-size:12px;font-weight:600;color:#64748b;margin:14px 0 8px;text-transform:uppercase;letter-spacing:.5px">
        Source Config
      </div>
      <div class="grid-2">
        <div>
          <label>Reddit subreddits (comma-separated)</label>
          <input v-model="form.reddit_subreddits" placeholder="sneakers, nba" />
        </div>
        <div>
          <label>Twitter queries (comma-separated)</label>
          <input v-model="form.twitter_queries" placeholder="#Nike, Nike shoes" />
        </div>
      </div>

      <div class="mt-4 flex gap-2">
        <button class="btn btn-primary" :disabled="!form.name || saving" @click="addEntity">
          {{ saving ? 'Creating…' : 'Create Entity' }}
        </button>
        <span v-if="error" style="color:#f87171;font-size:12px;align-self:center">{{ error }}</span>
      </div>
    </div>

    <!-- Entity list -->
    <div v-if="entities.length" class="entity-grid">
      <div v-for="e in entities" :key="e.id" class="entity-card card">
        <div class="flex" style="justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-weight:600;font-size:15px">{{ e.name }}</div>
            <div class="text-muted">{{ e.entity_type }} · {{ e.id?.slice(0,8) }}</div>
          </div>
          <span class="badge" :class="sentimentBadge(e.sentiment_score)">
            {{ formatScore(e.sentiment_score) }}
          </span>
        </div>
        <div v-if="e.description" class="text-muted mt-2" style="font-size:12px">{{ e.description }}</div>
        <div class="flex gap-2 mt-3" style="flex-wrap:wrap">
          <router-link :to="`/entity/${e.id}/ingest`" class="btn btn-secondary btn-sm">Ingest</router-link>
          <router-link :to="`/entity/${e.id}/graph`" class="btn btn-secondary btn-sm">Graph</router-link>
          <router-link :to="`/entity/${e.id}/personas`" class="btn btn-secondary btn-sm">Personas</router-link>
          <router-link :to="`/entity/${e.id}/simulation`" class="btn btn-primary btn-sm">Simulate →</router-link>
        </div>
      </div>
    </div>
    <div v-else-if="!loadingEntities" class="text-muted" style="margin-top:8px">
      No entities yet. Add one above to get started.
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { graph as graphApi } from '../api/graph.js'

const entities = ref([])
const loadingEntities = ref(true)
const saving = ref(false)
const error = ref('')

const form = ref({
  name: '', entity_type: 'brand', description: '',
  keywords_raw: '', reddit_subreddits: '', twitter_queries: '',
})

async function loadEntities() {
  loadingEntities.value = true
  try {
    const r = await graphApi.listEntities()
    entities.value = r.data.entities || r.data || []
  } finally {
    loadingEntities.value = false
  }
}

async function addEntity() {
  error.value = ''
  saving.value = true
  try {
    const keywords = form.value.keywords_raw.split(',').map(s => s.trim()).filter(Boolean)
    const subreddits = form.value.reddit_subreddits.split(',').map(s => s.trim()).filter(Boolean)
    const twitter_queries = form.value.twitter_queries.split(',').map(s => s.trim()).filter(Boolean)
    await graphApi.createEntity({
      name: form.value.name,
      entity_type: form.value.entity_type,
      description: form.value.description,
      keywords,
      source_config: {
        reddit: { subreddits },
        twitter: { queries: twitter_queries },
      },
    })
    form.value = { name: '', entity_type: 'brand', description: '', keywords_raw: '', reddit_subreddits: '', twitter_queries: '' }
    await loadEntities()
  } catch (e) {
    error.value = e.response?.data?.error || e.message
  } finally {
    saving.value = false
  }
}

function sentimentBadge(score) {
  if (score == null) return 'badge-neutral'
  return score > 0.1 ? 'badge-positive' : score < -0.1 ? 'badge-negative' : 'badge-neutral'
}
function formatScore(s) {
  if (s == null) return 'N/A'
  return (s >= 0 ? '+' : '') + Number(s).toFixed(2)
}

onMounted(loadEntities)
</script>

<style scoped>
.entity-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.entity-card { display: flex; flex-direction: column; }
</style>
