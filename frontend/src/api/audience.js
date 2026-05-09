import api from './index.js'

export const audience = {
  // Method B — adjacent communities in a category corpus
  adjacent: (body) => api.post('/audience/adjacent', body),

  // Method C — competitor-only audiences + positioning gaps
  negativeSpace: (body) => api.post('/audience/negative-space', body),

  // Helper — pairwise audience overlap matrix only
  overlap: (body) => api.post('/audience/overlap', body),

  // Chunk 1 — Generate execution brief for a single audience
  // body: { target_entity_id, audience, source_method?, extra_context? }
  brief: (body) => api.post('/audience/brief', body, { timeout: 120000 }),
}
