import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api/v1`;

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' }
});

// Inject auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('as_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('as_token');
      localStorage.removeItem('as_user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// Auth
export const authAPI = {
  register: (email, password) => api.post('/auth/register', { email, password }),
  login: (email, password) => api.post('/auth/login', { email, password }),
  me: () => api.get('/auth/me'),
  createApiKey: (name) => api.post('/auth/api-keys', { name }),
  listApiKeys: () => api.get('/auth/api-keys'),
  revokeApiKey: (id) => api.delete(`/auth/api-keys/${id}`),
};

// Scraping
export const scrapeAPI = {
  individual: (url) => api.post('/scrape', { url }),
  bulk: (urls, callbackUrl) => api.post('/scrape/bulk', { urls, callback_url: callbackUrl }),
  bulkUpload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/scrape/bulk/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
};

// Jobs
export const jobsAPI = {
  get: (jobId) => api.get(`/jobs/${jobId}`),
  retry: (jobId) => api.post(`/jobs/${jobId}/retry`),
  getBulk: (bulkId) => api.get(`/jobs/bulk/${bulkId}`),
  getBulkItems: (bulkId) => api.get(`/jobs/bulk/${bulkId}/items`),
};

// Results
export const resultsAPI = {
  list: (params) => api.get('/results', { params }),
  get: (id) => api.get(`/results/${id}`),
  getByUrl: (url) => api.get('/results/by-url', { params: { url } }),
  update: (id, data) => api.put(`/results/${id}`, data),
  validate: (id) => api.post(`/results/${id}/validate`),
  getEvidence: (id) => api.get(`/results/${id}/evidence`),
  exportData: (format, params) => api.get('/results/export', {
    params: { format, ...params },
    responseType: format === 'json' ? 'json' : 'blob'
  }),
};

// Taxonomy
export const taxonomyAPI = {
  get: () => api.get('/taxonomy'),
  createCategory: (data) => api.post('/taxonomy/categories', data),
  updateCategory: (id, data) => api.put(`/taxonomy/categories/${id}`, data),
  createSubcategory: (data) => api.post('/taxonomy/subcategories', data),
  updateSubcategory: (id, data) => api.put(`/taxonomy/subcategories/${id}`, data),
  importTaxonomy: (data) => api.post('/taxonomy/import', data),
};

// Config
export const configAPI = {
  get: () => api.get('/config'),
  update: (data) => api.put('/config', data),
};

// Stats
export const statsAPI = {
  get: () => api.get('/stats'),
  operational: () => api.get('/stats/operational'),
};

// Docs
export const docsAPI = {
  get: () => api.get('/docs-info'),
};

// Screenshots
export const getScreenshotUrl = (path) => {
  if (!path) return null;
  return `${API_BASE}/screenshots/${path}`;
};

export default api;
