# BARROW.AI Architecture Documentation

## System Overview

BARROW.AI Backend is a production-grade FastAPI application designed for conversational AI with multi-channel support. This document provides technical architecture details.

## 🏗️ Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│              Presentation Layer                      │
│ • REST API Endpoints (26+ admin, chat endpoints)   │
│ • Swagger UI (/docs)                               │
│ • Health Check (/health)                           │
└─────────────┬───────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────┐
│            Application Layer (FastAPI)              │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Middleware Stack (6 layers)                    │ │
│ │ 1. Rate Limiting (per endpoint)                │ │
│ │ 2. Security Headers (CORS, CSP)                │ │
│ │ 3. Request Logging (structured)                │ │
│ │ 4. Error Handling (exception mapping)          │ │
│ │ 5. Metrics Collection (Prometheus)             │ │
│ │ 6. Authentication (JWT extraction)             │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Router: /api/v1/                               │ │
│ │ ├── /auth (login, 2FA, refresh)                │ │
│ │ ├── /admin (users, knowledge, analytics)       │ │
│ │ ├── /chat (conversation management)            │ │
│ │ └── /health (diagnostics)                      │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────┬───────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────┐
│              Service Layer                          │
│ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐  │
│ │ ChatService │ │ RAGService   │ │AdminService  │  │
│ │ • Routing   │ │ • Embeddings │ │ • Auth logic │  │
│ │ • Session   │ │ • Retrieval  │ │ • Users/perms│  │
│ │ • LLM calls │ │ • Scoring    │ │ • Audit logs │  │
│ └─────────────┘ └──────────────┘ └──────────────┘  │
│ ┌──────────────────┐ ┌──────────────────────────┐   │
│ │ Analytics Svc    │ │ WhatsApp Service         │   │
│ │ • Trends         │ │ • Message routing        │   │
│ │ • Sentiment      │ │ • Transcription (audio)  │   │
│ │ • Queries        │ │ • TTS synthesis          │   │
│ └──────────────────┘ └──────────────────────────┘   │
└─────────────┬───────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────┐
│            Repository Layer (Data Access)           │
│ • ConversationRepository                            │
│ • AdminRepository                                   │
│ • KnowledgeRepository                               │
│ • SessionRepository                                 │
│ (SQLAlchemy ORM + async transactions)               │
└─────────────┬───────────────────────────────────────┘
              │
┌─────────────┼──────────────┬──────────────┬─────────┐
│             │              │              │         │
▼             ▼              ▼              ▼         ▼
PostgreSQL   Redis         Qdrant        Gemini   Ollama
(Schema)     (Cache)       (Vectors)     (LLM)    (LLM)
```

## 💾 Database Architecture

### Schema Design

**Core Tables:**

1. **admin_users**
   ```sql
   id: UUID (PK)
   username: VARCHAR(255) UNIQUE
   email: VARCHAR(255) UNIQUE
   password_hash: VARCHAR(255) (Argon2id)
   role: ENUM (SUPERADMIN, ADMIN, AUDITOR, VIEWER)
   is_active: BOOLEAN
   created_at: TIMESTAMP
   updated_at: TIMESTAMP
   two_factor_enabled: BOOLEAN
   two_factor_secret: VARCHAR (encrypted)
   ```

2. **conversations**
   ```sql
   id: UUID (PK)
   session_id: UUID (FK → sessions)
   user_id: VARCHAR
   source: ENUM (web, whatsapp)
   status: ENUM (active, resolved, abandoned)
   messages: JSONB (array of {role, content, timestamp})
   response_time: INTEGER (ms)
   feedback: JSONB {rating, sentiment, comment}
   created_at: TIMESTAMP
   updated_at: TIMESTAMP
   
   INDEXES:
   - idx_conversations_status
   - idx_conversations_created_at_range
   - idx_conversations_session_created
   - idx_conversations_feedback_nonnull
   ```

3. **knowledge_documents**
   ```sql
   id: UUID (PK)
   title: VARCHAR(255)
   content: TEXT
   file_type: VARCHAR (pdf, txt, md, docx)
   uploaded_by: UUID (FK → admin_users)
   is_active: BOOLEAN
   created_at: TIMESTAMP
   updated_at: TIMESTAMP
   ```

4. **knowledge_chunks**
   ```sql
   id: UUID (PK)
   document_id: UUID (FK → knowledge_documents)
   chunk_index: INTEGER
   content: TEXT
   embedding: VECTOR (384) [via Qdrant]
   created_at: TIMESTAMP
   ```

5. **audit_logs**
   ```sql
   id: UUID (PK)
   admin_id: UUID (FK → admin_users)
   action: VARCHAR (create, update, delete, view)
   resource_type: VARCHAR (user, document, conversation)
   resource_id: VARCHAR
   changes: JSONB
   ip_address: VARCHAR
   user_agent: VARCHAR
   created_at: TIMESTAMP
   
   INDEXES:
   - idx_audit_logs_admin_id
   - idx_audit_logs_admin_severity
   - idx_audit_logs_created_at
   ```

### Migration Strategy

Located in `alembic/versions/`:
- `001_initial_schema.py` - Core tables
- `002_add_performance_indexes.py` - Initial indexes
- `003_add_qdrant_integration.py` - Vector support
- `004_add_performance_indexes.py` - Analytics optimization

Run with: `alembic upgrade head`

## 🔐 Security Architecture

### Authentication Flow

```
User Input
   ↓
[POST /auth/login]
   ↓
Verify Credentials (Argon2id)
   ↓
2FA Required?
   ├─ Yes → [POST /auth/2fa/verify] → Verify TOTP
   └─ No → Continue
   ↓
Generate JWT Token
   ├ Sign with HS256
   ├ Exp: 1 hour
   └ Claim: {user_id, role, 2fa_verified}
   ↓
Return Token + Set HttpOnly Cookie
   ↓
Store Session in Redis (15-min TTL)
```

### Authorization Model (RBAC)

**Roles & Permissions:**

| Role | Auth | Users | Knowledge | Analytics | Audit | 2FA Mgmt |
|------|------|-------|-----------|-----------|-------|----------|
| SUPERADMIN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| AUDITOR | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| VIEWER | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ |

### Rate Limiting Strategy

Per-endpoint configuration using Redis sliding window:

```python
# Configuration
{
    "/api/v1/auth/login": {"limit": 5, "window": 60},      # 5/min
    "/api/v1/admin/knowledge/upload": {"limit": 10, "window": 60},
    "/api/v1/admin/analytics/overview": {"limit": 30, "window": 60},
}

# Algorithm: INCR key + EXPIRE (sliding window)
```

## 📡 Service Integration

### LLM Provider Factory Pattern

```python
class LLMProvider(ABC):
    async def generate(prompt, **kwargs) -> str
    
class GeminiProvider(LLMProvider):
    # Uses google-generativeai 0.8.3
    # Model: askbarrow-npp-v3 (fine-tuned)
    # Retry: tenacity with exponential backoff
    
class OllamaProvider(LLMProvider):
    # Local fallback
    # URL: http://ollama:11434
    # Model: mistral or equivalent
    
# Selection logic
provider = get_llm_provider()  # Env: ACTIVE_LLM_PROVIDER
```

### Embedding & Vector Search

```
Document Upload
   ↓
Split into chunks (512-token windows)
   ↓
Generate embeddings (BGE-base-v1.5, 384 dims)
   ↓
Store in Qdrant collection
   ├ Collection: "knowledge"
   ├ Metric: cosine
   └ Point count: variable
   
User Query
   ↓
Embed query (same model)
   ↓
Search Qdrant (threshold: 0.7, top_k: 5)
   ↓
Retrieve context
   ↓
Augment prompt → LLM generation
```

## 🚀 Performance Optimizations

### Caching Strategy

**Layer 1: HTTP Cache** (Redis)
- Session tokens: 15-min TTL
- Conversation metadata: 5-min TTL
- Knowledge summaries: 24-hour TTL
- Namespace isolation via CacheNamespace enum

**Layer 2: Database Indexes**
- 7 indexes on high-query tables
- Covering indexes for common queries
- Partial indexes for feedback analysis

**Layer 3: Application Cache**
- Embedding model cached in memory
- LLM provider singleton (with safeguards)
- Connection pool reuse (20 connections)

### Query Optimization

**Common Patterns:**

```python
# Trend analysis (daily aggregation)
SELECT created_at::DATE, COUNT(*) FROM conversations
GROUP BY created_at::DATE
ORDER BY created_at DESC

# Sentiment distribution (grouped feedback)
SELECT feedback, COUNT(*) FROM conversations
WHERE feedback IS NOT NULL AND created_at > ?
GROUP BY feedback

# Top performers (latency percentiles)
SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time)
FROM conversations
WHERE created_at > ?
```

## 📊 Monitoring & Observability

### Structured Logging

```json
{
  "timestamp": "2026-05-18T14:30:00.123Z",
  "level": "INFO",
  "logger": "app.services.chat_service",
  "message": "Chat endpoint invoked",
  "event": "chat_request_received",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "channel": "web",
  "duration_ms": 234,
  "cache_hit": true,
  "tags": ["performance", "user-interaction"]
}
```

### Metrics Exposed

- HTTP request duration (histogram)
- Database query count (counter)
- Cache hit rate (gauge)
- Active connections (gauge)
- LLM response time (histogram)
- Vector search latency (histogram)

## 🔄 Deployment Topology

### Production Environment

```
[Internet] → [Traefik Reverse Proxy]
                    ↓
        ┌─────────────┴────────────┐
        ↓                          ↓
    [App Pod 1]          [App Pod 2]
    (FastAPI)            (FastAPI)
        ↓                          ↓
        └─────────────┬────────────┘
                      ↓
        ┌─────────────┴──────────┬──────────┬────────┐
        ↓                        ↓          ↓        ↓
    PostgreSQL              Redis         Qdrant  Gemini
   (Primary)              (Cluster)    (Vector DB) (Cloud)
   [Backup]                                        [Ollama]
```

### High Availability

- **Database**: Read replicas with connection pooling
- **Cache**: Redis cluster with sentinel
- **App**: Horizontal scaling via load balancer
- **Qdrant**: Snapshot backups daily

## 📝 Configuration Management

**Priority Order:**
1. Environment variables (highest)
2. `.env` file
3. `app/core/config.py` defaults (lowest)

**Key Configs:**
- `ENVIRONMENT`: production|development|testing
- `DATABASE_URL`: PostgreSQL async connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: Signing key (min 32 chars)
- `GEMINI_API_KEY`: LLM provider credential

## 🔗 External Dependencies

| Dependency | Purpose | Version | Alternative |
|-----------|---------|---------|-------------|
| PostgreSQL | Primary data store | 13+ | N/A |
| Redis | Cache & sessions | 6+ | Memcached |
| Qdrant | Vector database | 1.12+ | Pinecone, Weaviate |
| Google Gemini | LLM | 3.0 Flash | Ollama (local) |
| FastAPI | Web framework | 0.115+ | Starlette |
| SQLAlchemy | ORM | 2.0+ | Tortoise, Piccolo |

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-18  
**Related:** See README.md for deployment and development guides
