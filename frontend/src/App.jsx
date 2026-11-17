import { useCallback, useEffect, useState } from 'react'

import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Code2,
  Database,
  ExternalLink,
  FileText,
  Filter,
  LayoutDashboard,
  LoaderCircle,
  MapPin,
  Menu,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  WandSparkles,
  X,
  AlertCircle,
  RefreshCw,
} from 'lucide-react'

import { api } from './api'
import './App.css'


const PAGE_SIZE = 20

const CATEGORIES = [
  'programming_language',
  'framework',
  'library',
  'database',
  'cloud',
  'devops',
  'tool',
  'methodology',
  'concept',
  'other',
]

const CATEGORY_LABELS = {
  programming_language: 'Programming language',
  framework: 'Framework',
  library: 'Library',
  database: 'Database',
  cloud: 'Cloud',
  devops: 'DevOps',
  tool: 'Tool',
  methodology: 'Methodology',
  concept: 'Concept',
  other: 'Other',
  software_engineering: 'Software engineering',
  data_engineering: 'Data engineering',
  data_science: 'Data science',
  machine_learning: 'Machine learning',
  cloud_engineering: 'Cloud engineering',
  cybersecurity: 'Cybersecurity',
  quality_assurance: 'Quality assurance',
  it_support: 'IT support',
  professional_services: 'Professional services',
  human_resources: 'Human resources',
  sales: 'Sales',
  marketing: 'Marketing',
  consulting: 'Consulting',
  executive_management: 'Executive management',
}

function categoryLabel(value) {
  if (!value) return 'Unclassified'

  return (
    CATEGORY_LABELS[value] ||
    value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
  )
}

function initials(value) {
  if (!value) return 'NA'

  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

function formatDate(value) {
  if (!value) return 'Recently added'

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return 'Recently added'

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

function SourceBadge({ source }) {
  const normalized = (source || 'unknown').toLowerCase()

  return (
    <span className={`source-badge source-${normalized}`}>
      <span className="source-dot" />
      {normalized}
    </span>
  )
}

function RequirementBadge({ requirement }) {
  return (
    <span className={`requirement-badge requirement-${requirement || 'mentioned'}`}>
      {requirement || 'mentioned'}
    </span>
  )
}

function MetricCard({ icon: Icon, label, value, detail, tone }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}>
        <Icon size={19} strokeWidth={2} />
      </div>

      <div className="metric-copy">
        <span className="metric-label">{label}</span>
        <strong className="metric-value">
          {Number(value || 0).toLocaleString('en-US')}
        </strong>
        <span className="metric-detail">{detail}</span>
      </div>
    </article>
  )
}

function JobRow({ job, onOpen }) {
  return (
    <article className="job-row">
      <div className="company-mark">
        {initials(job.company)}
      </div>

      <div className="job-row-main">
        <button className="job-title-button" onClick={() => onOpen(job)}>
          {job.title}
        </button>

        <div className="job-meta-line">
          <span><Building2 size={13} />{job.company || 'Unknown company'}</span>
          <span><MapPin size={13} />{job.location || 'Location not specified'}</span>
        </div>

        <div className="job-badges">
          <SourceBadge source={job.source} />

          {job.is_active ? (
            <span className="status-badge active"><span />Active</span>
          ) : (
            <span className="status-badge inactive"><span />Inactive</span>
          )}
        </div>
      </div>

      <div className="job-row-side">
        <span className="job-date">
          <Clock3 size={13} />
          {formatDate(job.last_seen_at)}
        </span>

        <button className="icon-action" onClick={() => onOpen(job)} aria-label="View job">
          <ArrowUpRight size={18} />
        </button>
      </div>
    </article>
  )
}

function EmptyState({ icon: Icon = Search, title, message }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={24} /></div>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  )
}

function App() {
  const [page, setPage] = useState('overview')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const [apiStatus, setApiStatus] = useState('checking')
  const [error, setError] = useState('')

  const [statistics, setStatistics] = useState(null)
  const [recentJobs, setRecentJobs] = useState([])
  const [topSkills, setTopSkills] = useState([])
  const [dashboardLoading, setDashboardLoading] = useState(true)

  const [jobs, setJobs] = useState([])
  const [jobsTotal, setJobsTotal] = useState(0)
  const [jobsLoading, setJobsLoading] = useState(false)
  const [jobSearch, setJobSearch] = useState('')
  const [appliedJobSearch, setAppliedJobSearch] = useState('')
  const [jobsOffset, setJobsOffset] = useState(0)
  const [sourceFilter, setSourceFilter] = useState('all')

  const [skills, setSkills] = useState([])
  const [skillsTotal, setSkillsTotal] = useState(0)
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillSearch, setSkillSearch] = useState('')
  const [appliedSkillSearch, setAppliedSkillSearch] = useState('')
  const [skillCategory, setSkillCategory] = useState('')

  const [selectedSkill, setSelectedSkill] = useState(null)
  const [selectedSkillJobs, setSelectedSkillJobs] = useState([])
  const [skillJobsLoading, setSkillJobsLoading] = useState(false)

  const [selectedJob, setSelectedJob] = useState(null)
  const [jobAnalysis, setJobAnalysis] = useState(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisMissing, setAnalysisMissing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')

  const loadDashboard = useCallback(async () => {
    setDashboardLoading(true)
    setError('')

    try {
      const [health, stats, jobResult, skillResult] = await Promise.all([
        api.getHealth(),
        api.getStatistics(),
        api.getJobs({ limit: 6 }),
        api.getSkills({ limit: 6 }),
      ])

      setApiStatus(health.status === 'healthy' ? 'online' : 'offline')
      setStatistics(stats)
      setRecentJobs(jobResult.items || [])
      setTopSkills(skillResult.items || [])
      setSkillsTotal(skillResult.total || 0)
    } catch (err) {
      setApiStatus('offline')
      setError(err.message)
    } finally {
      setDashboardLoading(false)
    }
  }, [])

  const loadJobs = useCallback(async (query, source, offset) => {
    setJobsLoading(true)
    setError('')

    try {
      const result = await api.getJobs({
        q: query,
        source: source === 'all' ? '' : source,
        limit: PAGE_SIZE,
        offset,
      })

      setJobs(result.items || [])
      setJobsTotal(result.total || 0)
      setApiStatus('online')
    } catch (err) {
      setError(err.message)
      setApiStatus('offline')
    } finally {
      setJobsLoading(false)
    }
  }, [])

  const loadSkills = useCallback(async (query, category) => {
    setSkillsLoading(true)
    setError('')

    try {
      const result = await api.getSkills({
        q: query,
        category,
        limit: 100,
      })

      setSkills(result.items || [])
      setSkillsTotal(result.total || 0)
      setApiStatus('online')
    } catch (err) {
      setError(err.message)
      setApiStatus('offline')
    } finally {
      setSkillsLoading(false)
    }
  }, [])

  useEffect(() => {
    const task = Promise.resolve().then(loadDashboard)
    return () => task.catch(() => {})
  }, [loadDashboard])

  useEffect(() => {
    if (page === 'jobs') {
      void Promise.resolve().then(() => loadJobs(appliedJobSearch, sourceFilter, jobsOffset))
    }
  }, [page, appliedJobSearch, sourceFilter, jobsOffset, loadJobs])

  useEffect(() => {
    if (page === 'skills') {
      void Promise.resolve().then(() => loadSkills(appliedSkillSearch, skillCategory))
    }
  }, [page, appliedSkillSearch, skillCategory, loadSkills])

  const visibleJobs = jobs

  async function openJob(job) {
    setSelectedJob(job)
    setJobAnalysis(null)
    setAnalysisMissing(false)
    setAnalysisError('')
    setAnalysisLoading(true)

    try {
      const result = await api.getJobAnalysis(job.id)
      setJobAnalysis(result)
    } catch (err) {
      if (err.status === 404) {
        setAnalysisMissing(true)
      } else {
        setAnalysisError(err.message)
      }
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function openSkill(skill) {
    setSelectedSkill(skill)
    setSelectedSkillJobs([])
    setSkillJobsLoading(true)

    try {
      const result = await api.getSkillJobs(skill.id, {
        activeOnly: false,
        limit: 100,
      })

      setSelectedSkillJobs(result.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setSkillJobsLoading(false)
    }
  }

  function navigate(destination) {
    setPage(destination)
    setMobileMenuOpen(false)
    setError('')
  }

  function handleJobSearch(event) {
    event.preventDefault()
    setJobsOffset(0)
    setAppliedJobSearch(jobSearch.trim())
  }

  function handleSourceChange(event) {
    setSourceFilter(event.target.value)
    setJobsOffset(0)
  }

  function handleSkillSearch(event) {
    event.preventDefault()
    setAppliedSkillSearch(skillSearch.trim())
    setSelectedSkill(null)
    setSelectedSkillJobs([])
  }

  const pageInfo = {
    overview: {
      title: 'Overview',
      subtitle: 'Your job market intelligence workspace',
    },
    jobs: {
      title: 'Job Explorer',
      subtitle: 'Discover and analyze opportunities',
    },
    skills: {
      title: 'Skills Library',
      subtitle: 'Explore skills extracted from real job descriptions',
    },
  }[page]

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <BriefcaseBusiness size={21} />
            <span className="brand-spark"><Sparkles size={10} /></span>
          </div>

          <div>
            <strong>RoleRadar<span>AI</span></strong>
            <small>CAREER INTELLIGENCE</small>
          </div>

          <button
            className="mobile-close"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <div className="nav-label">WORKSPACE</div>

        <nav className="main-nav">
          <button
            className={`nav-item ${page === 'overview' ? 'active' : ''}`}
            onClick={() => navigate('overview')}
          >
            <LayoutDashboard size={18} />
            <span>Overview</span>
          </button>

          <button
            className={`nav-item ${page === 'jobs' ? 'active' : ''}`}
            onClick={() => navigate('jobs')}
          >
            <BriefcaseBusiness size={18} />
            <span>Job Explorer</span>
            <span className="nav-count">
              {(statistics?.active || 0).toLocaleString('en-US')}
            </span>
          </button>

          <button
            className={`nav-item ${page === 'skills' ? 'active' : ''}`}
            onClick={() => navigate('skills')}
          >
            <Code2 size={18} />
            <span>Skills Library</span>
            <span className="nav-count">{skillsTotal}</span>
          </button>
        </nav>

        <div className="sidebar-spacer" />

        <div className="sidebar-ai-card">
          <div className="sidebar-ai-icon"><WandSparkles size={17} /></div>
          <strong>Powered by Gemini</strong>
          <p>AI-assisted skill extraction from real job descriptions.</p>
        </div>

        <div className="sidebar-bottom">
          <div className="sidebar-api">
            <span className={`api-light ${apiStatus}`} />
            <span>{apiStatus === 'online' ? 'API connected' : apiStatus === 'checking' ? 'Connecting...' : 'API unavailable'}</span>
          </div>

          <div className="profile-row">
            <div className="profile-avatar">RR</div>
            <div className="profile-copy">
              <strong>RoleRadar Workspace</strong>
              <span>AI Job Intelligence</span>
            </div>
            <ShieldCheck size={17} className="profile-shield" />
          </div>
        </div>
      </aside>

      {mobileMenuOpen && (
        <button
          className="mobile-overlay"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Close menu"
        />
      )}

      <div className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu-button"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>

            <div>
              <div className="breadcrumb">Workspace <span>/</span> {pageInfo.title}</div>
              <h1>{pageInfo.title}</h1>
            </div>
          </div>

          <div className="topbar-right">
            <div className={`connection-pill ${apiStatus}`}>
              <span className="api-light" />
              {apiStatus === 'online' ? 'Live API' : apiStatus === 'checking' ? 'Connecting' : 'Offline'}
            </div>

            <div className="topbar-avatar"><Sparkles size={17} /></div>
          </div>
        </header>

        <main className="page-content">
          {error && (
            <div className="error-banner">
              <AlertCircle size={17} />
              <span>{error}</span>
              <button onClick={loadDashboard}><RefreshCw size={15} /> Retry</button>
            </div>
          )}

          {page === 'overview' && (
            <>
              <section className="welcome-banner">
                <div className="welcome-content">
                  <div className="eyebrow"><Sparkles size={14} /> AI-POWERED JOB INTELLIGENCE</div>
                  <h2>Find the roles that <span>move you forward.</span></h2>
                  <p>
                    Explore real opportunities, understand in-demand skills
                    and turn job market data into your next career move.
                  </p>

                  <button className="primary-button" onClick={() => navigate('jobs')}>
                    Explore opportunities <ArrowRight size={16} />
                  </button>
                </div>

                <div className="welcome-visual">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="visual-center"><WandSparkles size={38} /></div>
                  <div className="floating-chip chip-one"><Code2 size={15} /> Skills</div>
                  <div className="floating-chip chip-two"><BriefcaseBusiness size={15} /> Jobs</div>
                  <div className="floating-chip chip-three"><Activity size={15} /> Insights</div>
                </div>

                <div className="welcome-decoration" />
              </section>

              <div className="section-heading">
                <div>
                  <span className="section-kicker">LIVE WORKSPACE</span>
                  <h2>Market overview</h2>
                </div>
                <div className="updated-label"><span /> Connected to live job data</div>
              </div>

              {dashboardLoading ? (
                <div className="loading-panel"><LoaderCircle className="spin" size={24} /> Loading workspace data...</div>
              ) : (
                <>
                  <section className="metrics-grid">
                    <MetricCard
                      icon={BriefcaseBusiness}
                      label="Total jobs"
                      value={statistics?.total}
                      detail="Collected opportunities"
                      tone="purple"
                    />
                    <MetricCard
                      icon={CheckCircle2}
                      label="Active jobs"
                      value={statistics?.active}
                      detail="Currently available"
                      tone="green"
                    />
                    <MetricCard
                      icon={Clock3}
                      label="Inactive jobs"
                      value={statistics?.inactive}
                      detail="No longer active"
                      tone="orange"
                    />
                    <MetricCard
                      icon={Database}
                      label="Unique skills"
                      value={skillsTotal}
                      detail="Extracted by AI"
                      tone="blue"
                    />
                  </section>

                  <section className="dashboard-grid">
                    <div className="panel recent-panel">
                      <div className="panel-heading">
                        <div>
                          <h3>Recent opportunities</h3>
                          <p>Latest jobs collected by RoleRadar</p>
                        </div>

                        <button className="text-button" onClick={() => navigate('jobs')}>
                          View all <ArrowRight size={15} />
                        </button>
                      </div>

                      <div className="compact-job-list">
                        {recentJobs.length ? recentJobs.map((job) => (
                          <JobRow key={job.id} job={job} onOpen={openJob} />
                        )) : (
                          <EmptyState
                            icon={BriefcaseBusiness}
                            title="No jobs available"
                            message="Job listings will appear here after ingestion."
                          />
                        )}
                      </div>
                    </div>

                    <div className="side-stack">
                      <div className="panel source-panel">
                        <div className="panel-heading">
                          <div>
                            <h3>Data sources</h3>
                            <p>Active opportunities by source</p>
                          </div>
                          <Server size={18} className="panel-heading-icon" />
                        </div>

                        {Object.entries(statistics?.by_source || {}).map(([source, count]) => {
                          const max = Math.max(
                            ...Object.values(statistics?.by_source || { value: 1 }),
                            1,
                          )

                          return (
                            <div className="source-progress" key={source}>
                              <div className="progress-label">
                                <span>{source}</span>
                                <strong>{count.toLocaleString('en-US')}</strong>
                              </div>
                              <div className="progress-track">
                                <div
                                  className={`progress-fill fill-${source}`}
                                  style={{ width: `${(count / max) * 100}%` }}
                                />
                              </div>
                            </div>
                          )
                        })}
                      </div>

                      <div className="panel top-skills-panel">
                        <div className="panel-heading">
                          <div>
                            <h3>Popular skills</h3>
                            <p>Most frequently requested</p>
                          </div>
                          <Code2 size={18} className="panel-heading-icon" />
                        </div>

                        <div className="popular-skills">
                          {topSkills.length ? topSkills.map((skill) => (
                            <button
                              className="popular-skill"
                              key={skill.id}
                              onClick={() => {
                                navigate('skills')
                                openSkill(skill)
                              }}
                            >
                              <span className="skill-mini-icon"><Code2 size={14} /></span>
                              <span className="popular-skill-name">{skill.name}</span>
                              <span className="popular-skill-count">{skill.job_count}</span>
                            </button>
                          )) : (
                            <p className="muted-copy">No extracted skills yet.</p>
                          )}
                        </div>

                        <button className="text-button full-button" onClick={() => navigate('skills')}>
                          Explore skills <ArrowRight size={15} />
                        </button>
                      </div>
                    </div>
                  </section>
                </>
              )}
            </>
          )}

          {page === 'jobs' && (
            <>
              <section className="page-intro">
                <div>
                  <span className="section-kicker">OPPORTUNITY DISCOVERY</span>
                  <h2>Explore the job market</h2>
                  <p>Search job descriptions, compare opportunities and inspect AI-generated insights.</p>
                </div>
                <div className="intro-counter">
                  <BriefcaseBusiness size={18} />
                  <strong>{jobsTotal.toLocaleString('en-US')}</strong>
                  <span>matching jobs</span>
                </div>
              </section>

              <form className="filter-toolbar" onSubmit={handleJobSearch}>
                <div className="search-field">
                  <Search size={18} />
                  <input
                    value={jobSearch}
                    onChange={(event) => setJobSearch(event.target.value)}
                    placeholder="Search job title, company or description..."
                  />
                  {jobSearch && (
                    <button type="button" onClick={() => setJobSearch('')} aria-label="Clear search">
                      <X size={15} />
                    </button>
                  )}
                </div>

                <label className="select-filter">
                  <Filter size={16} />
                  <select value={sourceFilter} onChange={handleSourceChange}>
                    <option value="all">All sources</option>
                    <option value="greenhouse">Greenhouse</option>
                    <option value="lever">Lever</option>
                  </select>
                </label>

                <button className="primary-button search-submit" type="submit">
                  Search <ArrowRight size={15} />
                </button>
              </form>

              <div className="results-heading">
                <div>
                  <strong>{visibleJobs.length} jobs displayed</strong>
                  <span>Page {Math.floor(jobsOffset / PAGE_SIZE) + 1}</span>
                </div>
                <span className="results-note">Select a job to view its AI analysis</span>
              </div>

              {jobsLoading ? (
                <div className="loading-panel"><LoaderCircle className="spin" size={24} /> Loading job listings...</div>
              ) : visibleJobs.length ? (
                <div className="jobs-list">
                  {visibleJobs.map((job) => (
                    <JobRow key={job.id} job={job} onOpen={openJob} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Search}
                  title="No matching jobs"
                  message="Try another search term or select a different source."
                />
              )}

              <div className="pagination">
                <span>
                  Showing {jobsTotal ? jobsOffset + 1 : 0}–{Math.min(jobsOffset + PAGE_SIZE, jobsTotal)} of {jobsTotal}
                </span>

                <div>
                  <button
                    className="pagination-button"
                    disabled={jobsOffset === 0 || jobsLoading}
                    onClick={() => setJobsOffset(Math.max(0, jobsOffset - PAGE_SIZE))}
                  >
                    <ChevronLeft size={17} /> Previous
                  </button>

                  <button
                    className="pagination-button"
                    disabled={jobsOffset + PAGE_SIZE >= jobsTotal || jobsLoading}
                    onClick={() => setJobsOffset(jobsOffset + PAGE_SIZE)}
                  >
                    Next <ChevronRight size={17} />
                  </button>
                </div>
              </div>
            </>
          )}

          {page === 'skills' && (
            <>
              <section className="page-intro">
                <div>
                  <span className="section-kicker">AI SKILL INTELLIGENCE</span>
                  <h2>Explore the skills landscape</h2>
                  <p>Discover technical skills extracted from job postings and see where they are needed.</p>
                </div>
                <div className="intro-counter">
                  <Code2 size={18} />
                  <strong>{skillsTotal}</strong>
                  <span>unique skills</span>
                </div>
              </section>

              <form className="filter-toolbar" onSubmit={handleSkillSearch}>
                <div className="search-field">
                  <Search size={18} />
                  <input
                    value={skillSearch}
                    onChange={(event) => setSkillSearch(event.target.value)}
                    placeholder="Search skills..."
                  />
                  {skillSearch && (
                    <button type="button" onClick={() => setSkillSearch('')} aria-label="Clear search">
                      <X size={15} />
                    </button>
                  )}
                </div>

                <label className="select-filter">
                  <Filter size={16} />
                  <select
                    value={skillCategory}
                    onChange={(event) => {
                      setSkillCategory(event.target.value)
                      setSelectedSkill(null)
                    }}
                  >
                    <option value="">All categories</option>
                    {CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {categoryLabel(category)}
                      </option>
                    ))}
                  </select>
                </label>

                <button className="primary-button search-submit" type="submit">
                  Search <ArrowRight size={15} />
                </button>
              </form>

              <div className="skills-layout">
                <section className="panel skills-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Skills catalog</h3>
                      <p>{skillsTotal} skills in the database</p>
                    </div>
                    <Database size={18} className="panel-heading-icon" />
                  </div>

                  {skillsLoading ? (
                    <div className="loading-panel"><LoaderCircle className="spin" size={22} /> Loading skills...</div>
                  ) : skills.length ? (
                    <div className="skills-list">
                      {skills.map((skill) => (
                        <button
                          className={`skill-row ${selectedSkill?.id === skill.id ? 'selected' : ''}`}
                          key={skill.id}
                          onClick={() => openSkill(skill)}
                        >
                          <span className="skill-icon"><Code2 size={17} /></span>
                          <span className="skill-row-copy">
                            <strong>{skill.name}</strong>
                            <small>{categoryLabel(skill.category)}</small>
                          </span>
                          <span className="skill-row-count">{skill.job_count} jobs</span>
                          <ArrowRight size={16} className="skill-row-arrow" />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <EmptyState icon={Code2} title="No skills found" message="Try a different search or category." />
                  )}
                </section>

                <section className="panel skill-detail-panel">
                  {selectedSkill ? (
                    <>
                      <div className="panel-heading">
                        <div>
                          <span className="section-kicker">SKILL DETAILS</span>
                          <h3>{selectedSkill.name}</h3>
                          <p>{categoryLabel(selectedSkill.category)}</p>
                        </div>
                        <span className="skill-detail-icon"><Code2 size={21} /></span>
                      </div>

                      <div className="skill-detail-stat">
                        <strong>{selectedSkill.job_count}</strong>
                        <span>associated job postings</span>
                      </div>

                      <div className="divider" />

                      <div className="panel-subheading">
                        <h4>Related opportunities</h4>
                        <span>{selectedSkillJobs.length} results</span>
                      </div>

                      {skillJobsLoading ? (
                        <div className="loading-panel"><LoaderCircle className="spin" size={22} /> Loading related jobs...</div>
                      ) : selectedSkillJobs.length ? (
                        <div className="related-jobs">
                          {selectedSkillJobs.map((job) => (
                            <article className="related-job" key={job.job_id}>
                              <div className="related-job-main">
                                <strong>{job.title}</strong>
                                <span>{job.company || 'Unknown company'} · {job.source}</span>
                                <p>{job.evidence}</p>
                              </div>
                              <div className="related-job-side">
                                <RequirementBadge requirement={job.requirement} />
                                <button
                                  className="icon-action"
                                  onClick={() => openJob({
                                    id: job.job_id,
                                    title: job.title,
                                    company: job.company,
                                    location: job.location,
                                    description: job.description,
                                    source: job.source,
                                    url: job.url,
                                    is_active: job.is_active,
                                  })}
                                  aria-label="Open job analysis"
                                >
                                  <ArrowUpRight size={17} />
                                </button>
                              </div>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <EmptyState
                          icon={BriefcaseBusiness}
                          title="No related jobs"
                          message="There are no job associations for this skill yet."
                        />
                      )}
                    </>
                  ) : (
                    <div className="skill-placeholder">
                      <div className="placeholder-art"><Code2 size={32} /></div>
                      <h3>Select a skill</h3>
                      <p>Choose a skill from the catalog to discover related job opportunities and requirements.</p>
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
        </main>

        <footer className="app-footer">
          <span>© 2026 RoleRadar AI</span>
          <span><Sparkles size={13} /> Intelligent Job Discovery & Career Matching</span>
          <span className="footer-version">v0.1.0</span>
        </footer>
      </div>

      {selectedJob && (
        <div className="drawer-backdrop" onMouseDown={() => setSelectedJob(null)}>
          <aside
            className="detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Job details and AI analysis"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="drawer-header">
              <div className="drawer-header-label">
                <span className="section-kicker">JOB INTELLIGENCE</span>
                <span className="drawer-job-id">JOB #{selectedJob.id}</span>
              </div>

              <button className="drawer-close" onClick={() => setSelectedJob(null)} aria-label="Close details">
                <X size={19} />
              </button>
            </div>

            <div className="drawer-job-heading">
              <div className="company-mark large">{initials(selectedJob.company)}</div>
              <div>
                <h2>{selectedJob.title}</h2>
                <p><Building2 size={14} /> {selectedJob.company || 'Unknown company'}</p>
                <p><MapPin size={14} /> {selectedJob.location || 'Location not specified'}</p>
              </div>
            </div>

            <div className="drawer-job-tags">
              <SourceBadge source={selectedJob.source} />
              {selectedJob.is_active && <span className="status-badge active"><span />Active</span>}
            </div>

            <div className="drawer-actions">
              {selectedJob.url && (
                <a className="primary-button" href={selectedJob.url} target="_blank" rel="noreferrer">
                  Original listing <ExternalLink size={15} />
                </a>
              )}
            </div>

            <div className="divider" />

            <div className="analysis-heading">
              <div className="analysis-icon"><WandSparkles size={19} /></div>
              <div>
                <h3>Gemini AI Analysis</h3>
                <p>Structured insights from the job description</p>
              </div>
            </div>

            {analysisLoading ? (
              <div className="loading-panel"><LoaderCircle className="spin" size={22} /> Analyzing stored results...</div>
            ) : analysisMissing ? (
              <EmptyState
                icon={Sparkles}
                title="AI analysis not available"
                message="This job has not been analyzed yet. Its AI insights will appear here after processing."
              />
            ) : analysisError ? (
              <div className="analysis-error"><AlertCircle size={17} />{analysisError}</div>
            ) : jobAnalysis ? (
              <div className="analysis-content">
                <div className="analysis-summary">
                  <span className="section-kicker">AI SUMMARY</span>
                  <p>{jobAnalysis.summary}</p>
                </div>

                <div className="analysis-info-grid">
                  <div>
                    <span>Role category</span>
                    <strong>{categoryLabel(jobAnalysis.category)}</strong>
                  </div>
                  <div>
                    <span>Seniority</span>
                    <strong>{categoryLabel(jobAnalysis.seniority)}</strong>
                  </div>
                </div>

                <div className="analysis-skills-heading">
                  <h4>Extracted skills</h4>
                  <span>{jobAnalysis.skills.length} skills</span>
                </div>

                {jobAnalysis.skills.map((skill) => (
                  <div className="analysis-skill" key={skill.id}>
                    <div className="analysis-skill-top">
                      <div>
                        <strong>{skill.name}</strong>
                        <span>{categoryLabel(skill.category)}</span>
                      </div>
                      <RequirementBadge requirement={skill.requirement} />
                    </div>
                    <p className="evidence-text">“{skill.evidence}”</p>
                  </div>
                ))}

                <div className="analysis-footnote">
                  <CheckCircle2 size={15} />
                  Analyzed with {jobAnalysis.model_name}
                </div>
              </div>
            ) : null}

            <div className="drawer-description">
              <div className="analysis-skills-heading">
                <h4>Original description</h4>
                <FileText size={16} />
              </div>
              <p>{selectedJob.description || 'No description available.'}</p>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}

export default App
