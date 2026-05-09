import api from './index.js'

export const ingestion = {
  autoPull: (body) => api.post('/ingestion/auto-pull', body),
  pull: (body) => api.post('/ingestion/pull', body),
  getStatus: (taskId) => api.get(`/ingestion/status/${taskId}`),
  preview: (entityId, limit = 20) => api.get(`/ingestion/preview/${entityId}`, { params: { limit } }),
  schedule: (body) => api.post('/ingestion/schedule', body),
  deleteSchedule: (scheduleId) => api.delete(`/ingestion/schedule/${scheduleId}`),

  // BYO data upload (multipart) — bypass JSON axios config so we can send FormData
  upload: (entityId, file, opts = {}) => {
    const fd = new FormData()
    fd.append('entity_id', entityId)
    fd.append('file', file)
    if (opts.fileFormat) fd.append('file_format', opts.fileFormat)
    if (opts.columnMapping) fd.append('column_mapping', JSON.stringify(opts.columnMapping))
    if (opts.defaultPlatform) fd.append('default_platform', opts.defaultPlatform)
    return api.post('/ingestion/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
  },
}
