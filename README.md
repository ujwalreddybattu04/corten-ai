<p align="center">
  <img src="frontend/public/logo.svg" alt="Corten AI" width="80" />
</p>

<h1 align="center">Corten AI</h1>

<p align="center">
  <strong>AI-Powered Answer Engine</strong> — Search smarter. Get cited answers instantly.
</p>

<p align="center">
  Built by <strong>Chryselys Private Limited</strong>
</p>

<p align="center">
  <a href="#features">Features</a> &middot;
  <a href="#tech-stack">Tech Stack</a> &middot;
  <a href="#getting-started">Getting Started</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#contributing">Contributing</a>
</p>

---

## Features

- **AI Search Engine** — Ask anything in natural language, get direct answers with inline citations `[1][2]`
- **Smart Routing** — Queries are automatically classified (direct, quick, standard, deep research) and routed to the optimal pipeline
- **Tool System** — Modular tools (web search, calculator, weather, image search, URL reader) selected dynamically per query
- **Streaming Responses** — Token-by-token answer streaming via Server-Sent Events with real-time thinking indicators
- **Deep Research Agent** — Multi-step research for complex queries with sub-question decomposition
- **Threaded Conversations** — Follow-up questions with full context retention
- **Spaces** — Organize threads into workspaces by topic, project, or team with custom icons and colors
- **Discover** — Trending news with AI-powered article summaries and follow-up Q&A
- **History Dashboard** — Full-screen Grok-style history modal with search, time grouping, and conversation preview
- **Focus Modes** — Scope searches: All, Academic, YouTube, Reddit, Writing, Math
- **Analyst Workspace** — Sidebar entry and empty workspace shell, ready for workflows based on Chryselys requirements.

## Hosting

[Live app](https://corten-ai-web.onrender.com) · [Analyst Workspace](https://corten-ai-web.onrender.com/analyst-workspace) · [Backend health](https://corten-ai-api.onrender.com/health)

[Deploy the full setup on Render](https://render.com/deploy?repo=https://github.com/ujwalreddybattu04/corten-ai)

The repository includes a four-resource deployment: frontend, backend, PostgreSQL and Redis.
See [deployment instructions and preview limits](docs/deployment.md) before creating it.
Keep API keys in backend environment variables; local secrets are excluded from Git and Docker images.
See the [hosted verification report](docs/hosted-verification.md) for completed checks and current integration limits.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, Framer Motion, Vanilla CSS |
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL with pgvector, Redis |
| LLM | Groq (`openai/gpt-oss-20b` default), configurable providers |
| Search | Tavily API, Serper API |
| News | NewsAPI, Guardian API, OpenWeather |
| Streaming | Server-Sent Events (SSE) |
| Auth | JWT (HS256) + bcrypt |
| Migrations | Alembic |

## Getting Started

### Prerequisites

- Node.js 22+
- Python 3.12+
- PostgreSQL 15+ (or Supabase cloud)
- Redis 7+ (or Upstash cloud)

### Frontend

```bash
cd frontend
npm install
npm run dev -- -p 3005
# → http://localhost:3005
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the server
uvicorn src.main:app --reload --port 8002
# → http://localhost:8002/docs
```

### Environment Variables

Create `backend/.env` with:

```env
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
JWT_SECRET_KEY=your-secret
GROQ_API_KEY=gsk_...
TAVILY_API_KEY=tvly-...
SERPER_API_KEY=...
NEWSAPI_KEY=...
GUARDIAN_API_KEY=...
OPENWEATHER_API_KEY=...
```

Create `frontend/.env.local` with:

```env
NEXT_PUBLIC_API_URL=http://localhost:8002
```

## Architecture

```
corten-ai/
├── frontend/                    # Next.js 16 (TypeScript)
│   ├── src/app/                 # App Router pages
│   │   ├── search/              # Main search + thread page
│   │   ├── discover/            # News feed + article summaries
│   │   ├── spaces/              # Collaborative workspaces
│   │   ├── history/             # History dashboard
│   │   └── auth/                # Login / Signup
│   ├── src/components/
│   │   ├── layout/              # Sidebar, Header, HistoryModal
│   │   ├── thread/              # AnswerStream, ResearchProgress
│   │   └── spaces/              # SpaceCard, SpaceHeader
│   ├── src/hooks/               # useSearch, useSpaces
│   ├── src/styles/              # Component CSS files
│   └── src/config/              # Constants, branding
├── backend/                     # FastAPI (Python)
│   ├── src/api/v1/              # REST endpoints (search, threads, auth, spaces)
│   ├── src/services/
│   │   ├── agents/              # Smart Router, Research Agent
│   │   ├── llm_service.py       # Groq LLM streaming
│   │   ├── search_orchestrator.py  # Central query pipeline
│   │   └── thread_service.py    # Thread CRUD
│   ├── src/tools/               # Modular tool system
│   │   ├── search/              # Web search, URL reader
│   │   ├── compute/             # Calculator
│   │   ├── data/                # Weather
│   │   └── media/               # Image search
│   ├── src/models/              # SQLAlchemy ORM models
│   ├── src/config/              # Settings, prompts
│   └── alembic/                 # Database migrations
└── Makefile
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

## License

This project is licensed under the GNU GPL v3.0 — see the [LICENSE](LICENSE) file for details.
