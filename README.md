# Company Bot — Plateforme IA Conversationnelle Multi-Entreprise

> **Version :** 4.0.0 | **Stack :** FastAPI · PostgreSQL · Qdrant · Redis · RabbitMQ · Gemini · WhatsApp
> Plateforme de chatbot d entreprise basee sur RAG (Retrieval-Augmented Generation), deployable en 30 minutes pour n importe quelle organisation.

---

## Fonctionnalites

| Categorie | Fonctionnalite |
|-----------|---------------|
| **IA & RAG** | Pipeline RAG complet (Qdrant + embeddings multilingues `intfloat/multilingual-e5-large`) |
| **IA & RAG** | LLM Gemini (principal) avec fallback Groq automatique |
| **IA & RAG** | Reecri ture de requetes + detection de langue automatique |
| **IA & RAG** | Cache Redis des reponses RAG (TTL configurable) |
| **Multi-entreprise** | Configuration complete via `company.yaml` (zero code) |
| **Canaux** | API REST + WhatsApp Cloud API |
| **Vocal** | Speech-to-Text via Whisper (faster-whisper) + TTS via Edge TTS |
| **Admin** | Interface d administration avec RBAC et 2FA |
| **Securite** | JWT + refresh tokens, AES-256, CSRF, rate limiting |
| **Observabilite** | Prometheus + Grafana, logs JSON structures |
| **Infrastructure** | Docker Compose, migrations Alembic, healthchecks |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLIENTS                                      │
│              WhatsApp │ Widget Web │ API REST                    │
└──────────────┬────────┴────────────┴──────────┬─────────────────┘
               │                                │
    ┌──────────▼──────────┐        ┌────────────▼────────┐
    │   FastAPI Backend    │        │  RabbitMQ Worker    │
    │  (app/main.py:8000) │        │  (worker.py)        │
    └──────────┬──────────┘        └────────────┬────────┘
               │                                │
    ┌──────────▼────────────────────────────────▼─────────┐
    │                   ChatService                        │
    │  1. Validation entree    5. Retrieval RAG (Qdrant)  │
    │  2. Detection langue     6. Generation LLM (Gemini) │
    │  3. Detection intent     7. Validation sortie       │
    │  4. Cache Redis          8. Persistance (PostgreSQL) │
    └──────────┬──────────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────────────────────┐
    │              Services Infrastruc ture                │
    │  PostgreSQL │ Redis │ Qdrant │ RabbitMQ │ Whisper    │
    └─────────────────────────────────────────────────────┘
```

### Pipeline de traitement d un message

```
Message utilisateur
       │
       ▼
[1] Validation entree (securite, longueur, injection)
       │
       ▼
[2] Detection d intent (salutation, aide, stop...)
       │ (si intent detecte → reponse instantanee depuis company.yaml)
       │ (sinon → continue)
       ▼
[3] Cache Redis (reponse deja calculee ?)
       │ (cache hit → reponse immediate)
       │ (cache miss → continue)
       ▼
[4] QueryTransformer (detection langue + reecri ture optimale)
       │
       ▼
[5] RAG Retrieval (Qdrant vector search)
       │
       ▼
[6] Generation LLM (Gemini → fallback Groq)
       │
       ▼
[7] Validation sortie (longueur, contenu interdit)
       │
       ▼
[8] Cache + Persistance
       │
       ▼
Reponse a l utilisateur
```

---

## Demarrage Rapide

### Prerequis

- Docker + Docker Compose
- Cle API Google Gemini ([obtenir ici](https://ai.google.dev))
- (Optionnel) Compte WhatsApp Business API

### Installation en 5 etapes

```bash
# 1. Cloner
git clone https://github.com/laurentmd5/bai-backend.git mon-bot
cd mon-bot

# 2. Configurer l identite de l entreprise
nano company.yaml

# 3. Configurer les secrets
cp .env.example .env
nano .env

# 4. Lancer
docker compose up -d

# 5. Verifier
curl http://localhost:8000/health/live
```

### Configuration minimale `.env`

```bash
# Secrets (generer avec: openssl rand -hex 32)
JWT_SECRET=changeme_minimum_32_chars
JWT_REFRESH_SECRET=changeme_minimum_32_chars
ENCRYPTION_KEY=changeme_base64_32_bytes==
CSRF_SECRET=changeme_minimum_32_chars

# Mots de passe
POSTGRES_PASSWORD=mot_de_passe_fort
REDIS_PASSWORD=mot_de_passe_fort
RABBITMQ_PASSWORD=mot_de_passe_fort

# LLM
GEMINI_API_KEY=votre_cle_gemini

# Entreprise
APP_NAME=VOTRE_ENTREPRISE Bot
QDRANT_COLLECTION=votre_entreprise_knowledge_v1
```

---

## Adapter pour une Nouvelle Entreprise

> Voir le guide complet : [ADAPTATION_GUIDE.md](./ADAPTATION_GUIDE.md)

**En resume (3 actions) :**

1. **Modifier `company.yaml`** — nom, bot_name, prompts, reponses pre-construites
2. **Modifier `.env`** — `APP_NAME`, `QDRANT_COLLECTION`, `CORS_ORIGINS`
3. **Reinitialiser Qdrant** et uploader les nouveaux documents via l interface admin

**Aucun fichier Python a modifier.**

---

## Structure du Projet

```
mon-bot/
├── company.yaml                    # ← IDENTITE ENTREPRISE (seul fichier metier)
├── .env                            # ← Secrets + variables infra
├── docker-compose.yml              # Orchestration des services
├── Dockerfile                      # Image Docker multi-stage
├── worker.py                       # Worker RabbitMQ (WhatsApp async)
│
├── app/
│   ├── main.py                     # Point d entree FastAPI
│   ├── core/
│   │   ├── company_config.py       # ← Singleton: charge company.yaml
│   │   ├── config.py               # Configuration Pydantic (variables .env)
│   │   ├── security.py             # JWT, CSRF, rate limiting
│   │   ├── metrics.py              # Metriques Prometheus
│   │   └── exceptions.py          # Exceptions typees
│   │
│   ├── services/
│   │   ├── chat_service.py         # Orchestrateur principal (pipeline complet)
│   │   ├── rag_service.py          # Retrieval-Augmented Generation
│   │   ├── whatsapp_service.py     # WhatsApp Cloud API
│   │   │
│   │   ├── llm/
│   │   │   ├── prompts.py          # Deleguant company_config
│   │   │   ├── gemini_provider.py  # Provider Gemini (principal)
│   │   │   ├── groq_provider.py    # Provider Groq (fallback)
│   │   │   └── query_transformer.py # Reecri ture de requetes + HyDE
│   │   │
│   │   ├── audio/
│   │   │   ├── whisper_service.py  # Speech-to-Text (faster-whisper)
│   │   │   └── tts_service.py      # Text-to-Speech (Edge TTS)
│   │   │
│   │   └── validation/
│   │       ├── input_validator.py  # Securite + normalisation entree
│   │       └── output_validator.py # Validation sortie LLM
│   │
│   ├── api/v1/endpoints/
│   │   ├── chat.py                 # POST /chat/message
│   │   ├── whatsapp.py             # GET|POST /whatsapp/webhook
│   │   └── admin/                  # Endpoints admin (auth, knowledge, analytics)
│   │
│   └── models/                     # Modeles SQLAlchemy + schemas Pydantic
│
└── alembic/                        # Migrations base de donnees
```

---

## API Reference

### Chat

```http
POST /api/v1/chat/message
Content-Type: application/json

{
  "message": "Quels services proposez-vous ?",
  "language": "fr",          # Optionnel (auto-detec te si absent)
  "session_id": "uuid"       # Optionnel (cree automatiquement)
}
```

**Reponse :**
```json
{
  "message": "Nous proposons des solutions reseaux...",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "sources": [{"document": "catalogue.pdf", "page": 3}],
  "confidence": 0.87,
  "cache_hit": false
}
```

### Feedback

```http
POST /api/v1/chat/feedback
{
  "conversation_id": "uuid",
  "feedback": 1              # 1 = positif, -1 = negatif
}
```

### Sante

```http
GET /health/live    # Liveness probe
GET /health/ready   # Readiness probe (verifie DB, Redis, Qdrant)
```

### Admin (JWT requis)

```http
POST   /api/v1/admin/auth/login
POST   /api/v1/admin/knowledge         # Upload document
GET    /api/v1/admin/knowledge         # Lister documents
DELETE /api/v1/admin/knowledge/{id}    # Supprimer document
GET    /api/v1/admin/analytics/overview
GET    /api/v1/admin/conversations
```

---

## Base de Connaissances (RAG)

### Formats acceptes
- PDF (`.pdf`) — recommande
- Word (`.docx`, `.doc`)
- Texte brut (`.txt`)
- Markdown (`.md`)
- Taille max : 50 MB par fichier

### Comment indexer des documents

**Via l API :**
```bash
curl -X POST https://votre-domaine.com/api/v1/admin/knowledge \
  -H "Authorization: Bearer [token]" \
  -F "file=@catalogue-services.pdf" \
  -F "title=Catalogue Services 2026" \
  -F "language=fr"
```

**Via l interface admin :** `https://votre-domaine.com/admin/knowledge`

### Parametres RAG

| Parametre | Description | Defaut |
|-----------|-------------|--------|
| `QDRANT_SIMILARITY_THRESHOLD` | Score minimum pour qu un document soit utilise | `0.70` |
| `QDRANT_TOP_K` | Nombre de chunks recuperes par requete | `10` |
| `RAG_CHUNK_SIZE` | Taille max d un chunk (tokens) | `400` |
| `RAG_CHUNK_OVERLAP` | Chevauchement entre chunks | `80` |

> **Conseil :** Si le bot repond souvent "Je n ai pas d information",
> baissez `QDRANT_SIMILARITY_THRESHOLD` a `0.40`.

---

## Variables d Environnement

### Obligatoires

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | Secret JWT (min 32 chars, generer: `openssl rand -hex 32`) |
| `JWT_REFRESH_SECRET` | Secret JWT refresh |
| `ENCRYPTION_KEY` | Cle AES-256 en base64 (`openssl rand -base64 32`) |
| `CSRF_SECRET` | Secret CSRF |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL |
| `REDIS_PASSWORD` | Mot de passe Redis |
| `RABBITMQ_PASSWORD` | Mot de passe RabbitMQ |
| `GEMINI_API_KEY` | Cle API Google Gemini |

### Importantes

| Variable | Description | Defaut |
|----------|-------------|--------|
| `APP_NAME` | Nom de l application (logs) | `Company Bot` |
| `ENVIRONMENT` | `development` / `staging` / `production` | `development` |
| `GEMINI_MODEL` | Modele Gemini | `gemini-2.5-flash-lite` |
| `QDRANT_COLLECTION` | Nom de la collection vectorielle | `company_knowledge_v1` |
| `CORS_ORIGINS` | Origines CORS autorisees | `["http://localhost:5173"]` |
| `QDRANT_SIMILARITY_THRESHOLD` | Seuil de similarite RAG | `0.70` |
| `COMPANY_CONFIG_PATH` | Chemin vers company.yaml | `company.yaml` |
| `WHATSAPP_VERIFY_TOKEN` | Token de verification WhatsApp | — |
| `WHATSAPP_ACCESS_TOKEN` | Token d acces WhatsApp | — |

---

## Infrastructure

### Services Docker

| Service | Image | Port | Role |
|---------|-------|------|------|
| `backend` | custom | 8000 | API FastAPI |
| `worker` | custom | — | Worker RabbitMQ |
| `postgres` | postgres:16-alpine | 5432 | Base de donnees |
| `redis` | redis:7-alpine | 6379 | Cache + sessions |
| `qdrant` | qdrant/qdrant | 6333 | Vecteurs (RAG) |
| `rabbitmq` | rabbitmq:3-management | 5672/15672 | File de messages |

### Commandes utiles

```bash
# Logs en temps reel
docker compose logs -f backend
docker compose logs -f worker

# Redemarrage propre
docker compose down && docker compose up -d

# Migration base de donnees
docker compose exec backend alembic upgrade head

# Sauvegarder la base de donnees
docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql

# Vider le cache Redis
docker compose exec redis redis-cli FLUSHDB
```

---

## Securite

- **Authentification :** JWT access (15 min) + refresh (7 jours)
- **2FA :** TOTP (Google Authenticator compatible) pour les admins
- **Chiffrement :** AES-256 pour les donnees sensibles (numeros de telephone)
- **Rate Limiting :** 30 msg/min (chat), 60/min (admin), 10/min (WhatsApp)
- **Anti-injection :** Detection de prompt injection, XSS, SQLi
- **CORS :** Origines configurables via `CORS_ORIGINS`
- **CSRF :** Protection CSRF sur toutes les mutations

> **Important :** Ne committez jamais le fichier `.env` avec de vrais secrets.
> Utilisez des gestionnaires de secrets (Vault, GitHub Secrets, etc.) en production.

---

## Observabilite

### Metriques Prometheus

Disponibles sur `/metrics` (protege en production) :

```
bot_chat_messages_total        # Messages traites par canal/langue
bot_chat_latency_ms            # Latence bout-en-bout
bot_llm_generation_duration_ms # Temps de generation LLM
bot_rag_retrieval_duration_seconds # Temps de recherche vectorielle
bot_cache_hit_ratio            # Taux de cache
bot_whatsapp_messages_total    # Messages WhatsApp
bot_error_total                # Erreurs par type
```

### Activer Grafana

```bash
docker compose --profile monitoring up -d
# Grafana disponible sur http://localhost:3000
```

---

## Modeles de Donnees (PostgreSQL)

| Table | Description |
|-------|-------------|
| `admin_users` | Comptes administrateurs avec RBAC et 2FA |
| `sessions` | Sessions utilisateurs (web + WhatsApp) |
| `conversations` | Historique des echanges (message + reponse + sources) |
| `knowledge_docs` | Metadata des documents indexes |
| `audit_logs` | Journal des actions admin |
| `whatsapp_optouts` | Numeros desabonnes |
| `jwt_blacklist` | Tokens revoques |

---

## Contribuer

1. Fork le depot
2. Creer une branche : `git checkout -b feature/ma-fonctionnalite`
3. Committer : `git commit -m "feat: ma nouvelle fonctionnalite"`
4. Pusher : `git push origin feature/ma-fonctionnalite`
5. Creer une Pull Request

### Conventions de commits

```
feat:     Nouvelle fonctionnalite
fix:      Correction de bug
refactor: Refactoring sans changement de comportement
docs:     Documentation uniquement
chore:    Maintenance (deps, CI, config)
```

---

## License

Proprietaire — Tous droits reserves.
