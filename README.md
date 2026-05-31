# BARROW.AI Backend

A high-performance FastAPI chatbot backend supporting WhatsApp integration with advanced NLP capabilities.

**Version:** 1.0.0  
**Status:** Production-Ready with Enhanced Analytics  
**Last Updated:** 2026-05-18

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Quick Start](#quick-start)
- [System Architecture](#system-architecture)
- [API Documentation](#api-documentation)
- [Development Guide](#development-guide)
- [Deployment](#deployment)
- [Contributing](#contributing)

---

## 📌 Project Overview

BARROW.AI is a sophisticated conversational AI system designed to provide intelligent responses across multiple channels (web, WhatsApp). The backend implements:

- **Multi-channel Support**: Web and WhatsApp integration
- **Advanced RAG Pipeline**: Vector-based document retrieval with Qdrant
- **Dual LLM Strategy**: Google Gemini 3.0 Flash with Ollama fallback
- **Enterprise Security**: Role-based access control (RBAC), 2FA, token management
- **Real-time Analytics**: Dashboard metrics with sentiment analysis
- **Scalable Architecture**: Async/await with Redis caching and database indexing

### Key Features

✅ **Authentication & Authorization**
- JWT Bearer tokens with HttpOnly cookies
- Two-Factor Authentication (TOTP + backup codes)
- Four-role RBAC system (SUPERADMIN, ADMIN, AUDITOR, VIEWER)
- Rate limiting per endpoint (5-30 requests/min based on operation)

✅ **Knowledge Management**
- Document ingestion and processing
- Automatic chunking and embedding generation
- Vector similarity search via Qdrant
- Deduplication and quality assurance

✅ **Admin Dashboard**
- 26+ management endpoints
- Conversation analytics (trends, sentiment, latency)
- User and session management
- Audit logging and compliance reporting

✅ **WhatsApp Integration**
- Message transcription via Faster-Whisper
- Text-to-speech synthesis via Edge-TTS
- Message routing and session tracking

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Docker & Docker Compose (recommended)
- PostgreSQL 13+
- Redis 6+
- 4GB RAM minimum

### Installation

#### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/your-org/barrow-ai-backend.git
cd barrow-ai-backend

# Build and start services
docker-compose up -d

# Run database migrations
docker exec barrow-ai-backend alembic upgrade head

# Verify health
curl http://localhost:8000/health
```

#### Option 2: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### First Request

```bash
# Create admin user
python scripts/create_admin.py --username admin --email admin@barrow.ai

# Login and get JWT token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}'

# Use token in subsequent requests
TOKEN="eyJhbGciOiJIUzI1NiIs..."
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/admin/users
```

---

## 🏗️ System Architecture

### Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend Layer                        │
│  (Web UI, WhatsApp Bot, Admin Dashboard)                    │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS/WebSocket
┌────────────────────▼────────────────────────────────────────┐
│                   Traefik Reverse Proxy                      │
│  (SSL, Load Balancing, Route Management)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     FastAPI Application                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Middleware Stack (6 layers)                         │   │
│  │ • Rate Limiting  • Security Headers • Logging       │   │
│  │ • Error Handling • CORS • Metrics                   │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Admin API (26 endpoints)                            │   │
│  │ • Auth (login, 2FA, token refresh)                  │   │
│  │ • Users (CRUD, role assignment)                     │   │
│  │ • Knowledge (docs, chunks, embeddings)              │   │
│  │ • Analytics (trends, sentiment, latency)            │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Core Services                                       │   │
│  │ • ChatService (conversation management)             │   │
│  │ • RAGService (document retrieval)                   │   │
│  │ • AdminService (user/session management)            │   │
│  │ • WhatsAppService (message routing)                 │   │
│  └─────────────────────────────────────────────────────┘   │
└────────┬──────────┬──────────────┬──────────┬────────────────┘
         │          │              │          │
┌────────▼─┐  ┌─────▼──┐  ┌───────▼──┐  ┌────▼─────┐
│PostgreSQL│  │ Redis  │  │ Qdrant   │  │ Gemini   │
│(Primary) │  │(Cache) │  │(Vectors) │  │API       │
└──────────┘  └────────┘  └──────────┘  └──────────┘
```

### Database Schema

**Core Tables:**
- `admin_users`: User accounts with roles and authentication
- `conversations`: Chat sessions with metadata (status, source, feedback)
- `knowledge_documents`: Uploaded documents with metadata
- `knowledge_chunks`: Document segments with embeddings
- `audit_logs`: Admin actions for compliance

**Indexes (Performance Optimization):**
```sql
-- Conversations
idx_conversations_status              -- Filtering by status
idx_conversations_created_at_range    -- Time-based queries
idx_conversations_session_created     -- Combined queries
idx_conversations_feedback_nonnull    -- Feedback analysis

-- Audit Logs
idx_audit_logs_admin_id               -- User audit trails
idx_audit_logs_admin_severity         -- Security alerts
idx_audit_logs_created_at             -- Time-based queries
```

### Caching Strategy

- **Session Cache**: 15-minute TTL via Redis
- **Token Blacklist**: Immediate revocation on logout
- **Rate Limiting**: Per-endpoint sliding window algorithm
- **Namespace**: Isolation via CacheNamespace enum (sessions, tokens, blacklist, etc.)

### Vector Database (Qdrant)

- **Embedding Model**: BGE Base v1.5 (384 dims, ~300MB)
- **Similarity Metric**: Cosine distance
- **Search Parameters**: threshold=0.7, top_k=5
- **Auto-indexed**: Collection created on first document upload

---

## 📚 API Documentation

### Authentication Endpoints

#### Login
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your_password"
}

Response: 200
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "requires_2fa": false
}
```

#### Two-Factor Authentication
```http
POST /api/v1/auth/2fa/verify
Authorization: Bearer {token}
Content-Type: application/json

{
  "code": "123456"
}

Response: 200
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "verified_at": "2026-05-18T14:30:00Z"
}
```

### Admin Endpoints

#### Get Overview Dashboard
```http
GET /api/v1/admin/analytics/overview?period=7d
Authorization: Bearer {token}

Response: 200
{
  "period": "7d",
  "conversations": {
    "total_conversations": 1,
    "conversations_by_channel": {"web": 1, "whatsapp": 0},
    "conversations_by_status": {"active": 1},
    "average_messages_per_conversation": 4.5
  },
  "sentiment": {
    "positive": {"count": 1, "percentage": 100.0},
    "neutral": {"count": 0, "percentage": 0.0},
    "negative": {"count": 0, "percentage": 0.0},
    "total_analyzed": 1
  },
  "latency_metrics": {
    "p50_ms": 285,
    "p95_ms": 892,
    "p99_ms": 2156
  }
}
```

#### Get Conversation Trends
```http
GET /api/v1/admin/analytics/trends?period=30d&granularity=day
Authorization: Bearer {token}

Response: 200
{
  "period": "30d",
  "granularity": "day",
  "data_points": [
    {
      "timestamp": "2026-05-18T00:00:00",
      "conversations": 42,
      "messages": 168,
      "avg_response_time_ms": 450,
      "sentiment": {"positive": 23, "neutral": 13, "negative": 6}
    }
  ]
}
```

#### Get Sentiment Analysis
```http
GET /api/v1/admin/analytics/sentiment?period=7d
Authorization: Bearer {token}

Response: 200
{
  "overall_sentiment": {
    "positive": {"count": 89, "percentage": 58.5},
    "neutral": {"count": 45, "percentage": 29.6},
    "negative": {"count": 18, "percentage": 11.8}
  },
  "by_channel": {...},
  "user_satisfaction": {
    "average_score": 4.2,
    "scale": "1-5"
  }
}
```

**Full API documentation**: See `docs/API.md` or visit `/docs` endpoint when server is running

---

## 🛠️ Development Guide

### Project Structure

```
barrow-ai-backend/
├── app/
│   ├── main.py                    # FastAPI app initialization
│   ├── api/
│   │   ├── v1/endpoints/
│   │   │   └── admin/             # Admin endpoints (8 files)
│   │   └── dependencies/          # Shared dependencies (auth, etc)
│   ├── models/
│   │   ├── domain/                # SQLAlchemy ORM models
│   │   ├── request/               # Request schemas
│   │   └── response/              # Response schemas
│   ├── services/
│   │   ├── chat_service.py        # Conversation management
│   │   ├── rag_service.py         # RAG pipeline
│   │   ├── admin_service.py       # Admin operations
│   │   ├── whatsapp_service.py    # WhatsApp integration
│   │   └── [subdirs]/             # Specialized services
│   ├── repositories/              # Database access layer
│   ├── middleware/                # Request/response processing
│   ├── core/                      # Configuration & utilities
│   └── utils/                     # Helper functions
├── alembic/
│   ├── versions/                  # Database migrations
│   └── env.py                     # Migration environment
├── tests/
│   ├── unit/                      # Unit tests
│   └── integration/               # Integration tests
├── scripts/
│   ├── create_admin.py            # Admin user creation
│   ├── seed_data.py               # Sample data loading
│   └── init_qdrant.py             # Vector DB initialization
├── docs/
│   ├── archive/                   # Archived reports
│   ├── API.md                     # API reference
│   ├── ARCHITECTURE.md            # System design
│   └── DEPLOYMENT.md              # Deployment guide
├── docker-compose.yml             # Production stack
├── docker-compose.dev.yml         # Development stack
└── requirements.txt               # Python dependencies
```

### Running Tests

```bash
# Run all tests with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_auth.py -v

# Run with markers
pytest tests/ -m "not slow" -v

# Run integration tests
pytest tests/integration/ --timeout=30
```

### Database Migrations

```bash
# Create new migration (auto-detect model changes)
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback one revision
alembic downgrade -1

# View migration history
alembic history
```

### Logging

Structured logging via `app.core.logging`:

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

logger.info("User login successful", user_id=user.id, source="web")
logger.warning("High latency detected", endpoint="/chat", latency_ms=5000)
logger.error("Database connection failed", error=str(e), retry_count=3)
```

### Environment Variables

Key configuration (see `.env.example`):

```env
# Server
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/barrow_ai
SQLALCHEMY_ECHO=false

# Redis
REDIS_URL=redis://redis:6379/0
SESSION_TIMEOUT=900

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# LLM
GEMINI_API_KEY=your_key_here
OLLAMA_BASE_URL=http://ollama:11434

# Security
JWT_SECRET_KEY=your_secret
JWT_ALGORITHM=HS256
JWT_EXPIRATION=3600

# WhatsApp
WHATSAPP_BUSINESS_PHONE_ID=your_phone_id
WHATSAPP_BUSINESS_ACCESS_TOKEN=your_token
```

---

## 📦 Deployment

### Production Deployment

#### Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

#### Environment Setup

```bash
# Create production environment file
cp .env.example .env
# Edit .env with production credentials

# Pull latest images
docker-compose pull

# Run migrations
docker-compose exec app alembic upgrade head

# Create admin user
docker-compose exec app python scripts/create_admin.py
```

### Monitoring

**Health Check Endpoint:**
```bash
curl http://localhost:8000/health
# Response:
# {
#   "status": "healthy",
#   "timestamp": "2026-05-18T14:30:00Z",
#   "database": "connected",
#   "redis": "connected",
#   "qdrant": "connected"
# }
```

**Metrics Endpoint:**
```bash
curl http://localhost:8000/metrics
# Prometheus-compatible metrics for monitoring
```

**Logs:**
- Centralized via Docker volumes at `/var/log/barrow-ai/`
- Structured JSON format for parsing
- Retention policy: 30 days

### Performance Tuning

**Database:**
- Connection pool size: 20 (default)
- Indexes optimized for analytics queries
- Query timeout: 30 seconds

**Caching:**
- Session TTL: 15 minutes
- Rate limit window: 60 seconds per endpoint
- Cache hit target: 75%+

**LLM:**
- Embedding model loaded on startup (8 seconds)
- Response timeout: 30 seconds
- Retry policy: 3 attempts with exponential backoff

---

## 🤝 Contributing

### Code Guidelines

- Follow PEP 8 style (enforced via Black formatter)
- Type hints required for all functions
- Docstrings for modules, classes, and public methods
- Tests required for all new features (minimum 80% coverage)

### Pull Request Process

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes and test: `pytest tests/`
3. Format code: `black app/ tests/`
4. Commit with conventional commits: `git commit -m "feat: add analytics endpoint"`
5. Push and create PR: `git push origin feature/your-feature`
6. Code review and CI/CD checks must pass

### Reporting Issues

- Security issues: Email security@barrow.ai (do not create public issues)
- Bugs: Create issue with reproduction steps and logs
- Features: Describe use case and acceptance criteria

---

## 📄 License

Proprietary - All rights reserved

---

## 📞 Support

- **Documentation**: See `docs/` directory
- **Issues**: GitHub Issues tracker
- **Email**: support@barrow.ai
- **Slack**: #barrow-ai-dev channel

---

## 🔄 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-05-18 | Initial release with analytics, improved indexes, real query implementation |
| 0.9.0 | 2026-05-15 | Beta release with core features |

---

**Last Reviewed:** 2026-05-18  
**Next Review:** 2026-06-18
