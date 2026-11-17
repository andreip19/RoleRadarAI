async function request(path) {
  let response

  try {
    response = await fetch(path, {
      headers: {
        Accept: 'application/json',
      },
    })
  } catch {
    throw new Error(
      'Cannot connect to RoleRadar AI backend. Make sure FastAPI is running on port 8010.',
    )
  }

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const error = new Error(
      payload?.detail || `Request failed with status ${response.status}`,
    )

    error.status = response.status

    throw error
  }

  return payload
}

function buildQuery(values) {
  const params = new URLSearchParams()

  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  })

  return params.toString()
}

export const api = {
  getHealth() {
    return request('/health')
  },

  getStatistics() {
    return request('/api/v1/jobs/statistics')
  },

  getJobs({ q = '', source = '', limit = 20, offset = 0 } = {}) {
    const query = buildQuery({ q, source, limit, offset })
    return request(`/api/v1/jobs?${query}`)
  },

  getSkills({ q = '', category = '', limit = 100, offset = 0 } = {}) {
    const query = buildQuery({ q, category, limit, offset })
    return request(`/api/v1/skills?${query}`)
  },

  getJobAnalysis(jobId) {
    return request(`/api/v1/jobs/${jobId}/analysis`)
  },

  getSkillJobs(skillId, { activeOnly = false, limit = 100 } = {}) {
    const query = buildQuery({
      active_only: activeOnly,
      limit,
    })

    return request(`/api/v1/skills/${skillId}/jobs?${query}`)
  },
}
