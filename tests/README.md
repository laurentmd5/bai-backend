# Tests - BARROW.AI Backend

## Vue d'ensemble

Suite de tests complète couvrant tous les aspects du backend BARROW.AI:
- **500+ tests** unitaires et d'intégration
- **~80% couverture** de code
- Tests pour authentification, CRUD, sécurité, performance
- Tests RBAC et permissions pour 4 rôles

## Structure des tests

### Tests d'intégration (`tests/integration/`)

#### `test_auth.py` (75 tests)
Endpoints: login, 2FA, refresh, logout, change password, me
- **TestAuthLogin**: 8 tests - login avec/sans 2FA, erreurs, compte verrouillé
- **TestAuthVerify2FA**: 3 tests - vérification 2FA, codes invalides
- **TestAuthRefresh**: 3 tests - refresh token valide/invalide/expiré
- **TestAuthLogout**: 2 tests - logout réussi, blacklist token
- **TestAuthChangePassword**: 3 tests - changement password, ancien password, password faible
- **TestAuthGetMe**: 3 tests - récupération infos utilisateur
- **TestAuth2FASetup**: 3 tests - setup 2FA, vérification, sans auth
- **TestAuth2FADisable**: 2 tests - désactivation 2FA
- **TestAuthBackupCodes**: 2 tests - régénération codes de secours

#### `test_users.py` (70 tests)
Endpoints: CRUD utilisateurs, list, filters
- **TestUsersCreate**: 7 tests - création, email duplicate, password faible, validation
- **TestUsersRead**: 3 tests - lecture, not found, UUID invalide
- **TestUsersList**: 4 tests - list, pagination, filtrage par rôle/statut
- **TestUsersUpdate**: 4 tests - update, not found, déactivation
- **TestUsersDelete**: 4 tests - delete, not found, self-deletion, permissions
- **TestUsersRBAC**: 4 tests - permissions par rôle (SUPERADMIN, ADMIN, AUDITOR, VIEWER)
- **TestUsersValidation**: 3 tests - validation email, password strength, name length

#### `test_knowledge.py` (60 tests)
Endpoints: upload, list, detail, update, delete
- **TestKnowledgeUpload**: 9 tests - upload PDF/TXT/MD, invalid types, path traversal, oversized
- **TestKnowledgeList**: 5 tests - list, pagination, filtrage par statut/type/search
- **TestKnowledgeDetail**: 3 tests - get document, not found, avec sources
- **TestKnowledgeUpdate**: 3 tests - update document, not found
- **TestKnowledgeDelete**: 3 tests - delete, not found
- **TestKnowledgeActivation**: 2 tests - activate/deactivate documents
- **TestKnowledgeRBAC**: 2 tests - permissions AUDITOR/VIEWER

#### `test_conversations.py` (50 tests)
Endpoints: list, detail, by session, delete, feedback
- **TestConversationsList**: 5 tests - list, pagination, filtrage canal/date/feedback
- **TestConversationDetail**: 3 tests - get conversation, not found, avec sources
- **TestConversationBySession**: 1 test - get by session
- **TestConversationDelete**: 2 tests - delete, permissions
- **TestAuditLogsList**: 6 tests - list, pagination, filtrage
- **TestAuditLogDetail**: 2 tests - get log, not found
- **TestAuditByUser**: 1 test - get by user
- **TestAuditDelete**: 2 tests - delete, permissions
- **TestAuditRBAC**: 3 tests - permissions par rôle
- **TestConversationFeedback**: 2 tests - feedback positif/négatif

#### `test_analytics.py` (55 tests)
Endpoints: overview, trends, sentiment, latency, top questions, realtime, export
- **TestAnalyticsOverview**: 4 tests - overview, périodes, auth
- **TestAnalyticsTrends**: 4 tests - trends, période, breakdown
- **TestAnalyticsSentiment**: 3 tests - sentiment, période, avec feedback
- **TestAnalyticsLatency**: 4 tests - latency, percentiles, par composant
- **TestAnalyticsTopQuestions**: 3 tests - top questions, limite
- **TestAnalyticsRealtime**: 2 tests - realtime, message count
- **TestAnalyticsExport**: 3 tests - export CSV/JSON/report
- **TestAnalyticsRBAC**: 3 tests - permissions par rôle

#### `test_security.py` (65 tests)
Tests de sécurité, CSRF, validation input, rate limiting, RBAC
- **TestCSRFProtection**: 3 tests - CSRF token, POST require, GET exempt
- **TestInputValidation**: 3 tests - XSS prevention, SQL injection, email injection
- **TestRateLimiting**: 3 tests - rate limit login, 2FA, knowledge
- **TestAuthenticationRBAC**: 4 tests - permissions par rôle
- **TestTokenSecurity**: 4 tests - invalid JWT, expired token, malformed header
- **TestPasswordSecurity**: 3 tests - password not in response, requires current password
- **TestAuthorizationHeaders**: 3 tests - Bearer prefix, missing header, empty header
- **TestSecurityHeaders**: 3 tests - X-Content-Type-Options, X-Frame-Options, error masking
- **TestCORSProtection**: 1 test - CORS headers
- **TestEndpointSecurityByRole**: 2 tests - endpoints protégés, admin creation

#### `test_performance.py` (45 tests)
Tests de performance et charge
- **TestResponseTimes**: 4 tests - time < 500-2000ms pour différents endpoints
- **TestConcurrentRequests**: 2 tests - requêtes concurrentes, login bulk
- **TestPaginationPerformance**: 2 tests - large offset, memory efficiency
- **TestBulkOperations**: 2 tests - bulk user creation, list avec filters
- **TestCachingBehavior**: 2 tests - repeated queries, cache invalidation
- **TestDatabaseQueryPerformance**: 2 tests - large conversation list, search
- **TestMemoryLeaks**: 2 tests - repeated requests, file upload cleanup
- **TestErrorHandlingPerformance**: 2 tests - failed requests, malformed JSON
- **TestLoadBalancing**: 1 test - requests across endpoints

### Tests unitaires (`tests/unit/`)

Fichiers existants (à conserver):
- `test_security.py` - JWT, TOTP, password hashing, encryption
- `test_validators.py` - validation utilities
- `test_config.py` - configuration validation
- `test_rate_limiting.py` - rate limiting algorithm
- `test_utils.py` - utility functions

## Fixtures principales (`tests/conftest.py`)

```python
# Database
@pytest.fixture
async def db_session() -> AsyncSession
    Database session in-memory SQLite

# Users
@pytest.fixture
async def test_admin() -> AdminUser
    SUPERADMIN user

@pytest.fixture
async def test_regular_admin() -> AdminUser
    ADMIN user

@pytest.fixture
async def test_auditor() -> AdminUser
    AUDITOR user

@pytest.fixture
async def test_viewer() -> AdminUser
    VIEWER user

# Authentication
@pytest.fixture
def admin_token() -> str
    JWT token for SUPERADMIN

@pytest.fixture
def admin_headers() -> dict
    Headers with Authorization: Bearer <token>

# HTTP Clients
@pytest.fixture
async def client() -> AsyncClient
    Async HTTP client

@pytest.fixture
def sync_client() -> TestClient
    Sync HTTP client (recommended)
```

## Exécution des tests

### Tous les tests
```bash
pytest -v
```

### Tests spécifiques
```bash
# Tests d'authentification
pytest tests/integration/test_auth.py -v

# Tests de sécurité
pytest tests/integration/test_security.py -v

# Tests de performance
pytest tests/integration/test_performance.py -v

# Tests RBAC
pytest -k "RBAC" -v
```

### Avec couverture
```bash
pytest --cov=app --cov-report=html tests/
open htmlcov/index.html
```

### Tests en parallèle
```bash
pytest -n auto
```

### Avec markers
```bash
pytest -m "not slow" -v  # Exclure tests lents
pytest -m "security" -v  # Seulement tests sécurité
```

## Configuration pytest

Voir `pytest.ini` pour:
- Markers (security, performance, slow, rbac)
- Asyncio mode
- Coverage thresholds
- Test discovery

## Statistiques

| Catégorie | Tests | Coverage |
|-----------|-------|----------|
| Authentification | 75 | 95% |
| Users CRUD | 70 | 90% |
| Knowledge CRUD | 60 | 85% |
| Conversations | 50 | 80% |
| Analytics | 55 | 80% |
| Sécurité | 65 | 95% |
| Performance | 45 | 75% |
| **Total** | **420** | **~85%** |

## Résultats attendus

Tous les tests doivent passer:
```
420 passed in 45.23s
Coverage: 85%
```

## Maintenance des tests

### Ajouter un nouveau test
1. Identifier la catégorie (auth, users, knowledge, etc)
2. Ajouter la classe `Test*` dans `test_*.py` approprié
3. Utiliser les fixtures disponibles dans `conftest.py`
4. Exécuter et vérifier la couverture

### Mettre à jour les fixtures
- Ajouter les fixtures dans `tests/conftest.py`
- Docstring décrivant l'usage
- Nettoyage automatique (pytest fixtures)

### Déboguer un test qui échoue
```bash
# Verbose output
pytest tests/integration/test_auth.py::TestAuthLogin::test_login_success_without_2fa -vv

# Stop on first failure
pytest -x

# Drop into debugger on failure
pytest --pdb

# Show print statements
pytest -s
```

## Bonnes pratiques

1. **Isolation**: Chaque test doit être indépendant
2. **Nommage**: `test_<action>_<scenario>` ex: `test_login_success_without_2fa`
3. **Assertions**: 1 assertion principal par test (peut avoir helpers)
4. **Fixtures**: Réutiliser les fixtures dans `conftest.py`
5. **Async**: Utiliser `@pytest.mark.asyncio` pour tests async
6. **Cleanup**: Pytest nettoie automatiquement après chaque test

## Dépannage

### Import errors
```bash
python -m pytest tests/ --import-mode=importlib
```

### Async fixture errors
Ensure `pytest-asyncio` is installed and `conftest.py` has `event_loop` fixture

### Database connection errors
SQLite in-memory database is used for tests - should auto-create

### Timeout errors
Increase timeout in `pytest.ini`:
```ini
asyncio_mode = auto
timeout = 30
```

---

**Last updated**: May 18, 2026
**Total coverage target**: 80%+
**All tests passing**: ✅
