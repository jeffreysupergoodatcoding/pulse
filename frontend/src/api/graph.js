import api from './index.js'

export const graph = {
  // Entity CRUD
  createEntity: (body) => api.post('/graph/entities', body),
  listEntities: () => api.get('/graph/entities'),
  getEntity: (id) => api.get(`/graph/entities/${id}`),

  // Graph operations
  build: (body) => api.post('/graph/build', body),
  getBuildStatus: (taskId) => api.get(`/graph/status/${taskId}`),
  getData: (entityId) => api.get(`/graph/${entityId}/data`),
  getOntology: (entityId) => api.get(`/graph/${entityId}/ontology`),
  getSentiment: (entityId) => api.get(`/graph/${entityId}/sentiment`),
  search: (entityId, body) => api.post(`/graph/${entityId}/search`, body),
}
