import api from './index.js'

export const ingestion = {
  autoPull: (body) => api.post('/ingestion/auto-pull', body),
  pull: (body) => api.post('/ingestion/pull', body),
  getStatus: (taskId) => api.get(`/ingestion/status/${taskId}`),
  preview: (entityId, limit = 20) => api.get(`/ingestion/preview/${entityId}`, { params: { limit } }),
  schedule: (body) => api.post('/ingestion/schedule', body),
  deleteSchedule: (scheduleId) => api.delete(`/ingestion/schedule/${scheduleId}`),
}
