import api from './index.js'

export const simulation = {
  create: (body) => api.post('/simulation/create', body),
  start: (simId, body) => api.post(`/simulation/${simId}/start`, body),
  getStatus: (simId) => api.get(`/simulation/${simId}/status`),
  stop: (simId) => api.post(`/simulation/${simId}/stop`),
  inject: (simId, body) => api.post(`/simulation/${simId}/inject`, body),
  getActions: (simId, params) => api.get(`/simulation/${simId}/actions`, { params }),
  getSentiment: (simId) => api.get(`/simulation/${simId}/sentiment`),
  getPrediction: (simId) => api.get(`/simulation/${simId}/prediction`),
}
