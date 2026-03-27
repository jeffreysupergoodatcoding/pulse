import api from './index.js'

export const persona = {
  generate: (body) => api.post('/persona/generate', body),
  getStatus: (taskId) => api.get(`/persona/status/${taskId}`),
  getSets: (entityId) => api.get(`/persona/${entityId}/sets`),
  getSet: (entityId, setId) => api.get(`/persona/${entityId}/set/${setId}`),
  getTemplates: () => api.get('/persona/templates'),
  fromTemplate: (body) => api.post('/persona/from_template', body),
}
