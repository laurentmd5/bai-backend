# Quick Start Guide for Developers

Welcome to BARROW.AI Backend! This guide will get you up and running in 5 minutes.

## ⚡ Quickest Setup (Docker)

```bash
# 1. Clone and navigate
git clone <repository>
cd barrow-ai-backend

# 2. Start all services
docker-compose up -d

# 3. Initialize database
docker-compose exec app alembic upgrade head

# 4. Create admin user
docker-compose exec app python scripts/create_admin.py --username admin

# 5. Done! Access the app
open http://localhost:8000/docs  # Swagger UI
open http://localhost:8000/health # Health check
```

## 🔑 Key Resources

| Need | Link |
|------|------|
| Full Documentation | [README.md](../README.md) |
| API Endpoints | http://localhost:8000/docs (when running) |
| Code Audit | [RAPPORT_AUDIT_EXHAUSTIF.md](../../RAPPORT_AUDIT_EXHAUSTIF.md) |
| Security Info | [SECURITY_AUDIT_REPORT.md](../../SECURITY_AUDIT_REPORT.md) |
| Test Guide | [GUIDE_EXECUTION_TESTS.md](../../GUIDE_EXECUTION_TESTS.md) |
| Rate Limits | [GUIDE_RATE_LIMITING.md](../../GUIDE_RATE_LIMITING.md) |
| Archived Reports | [This Directory](README.md) |

## 🚀 Common Tasks

### Run Tests
```bash
pytest tests/ --cov=app
```

### Create Database Migration
```bash
alembic revision --autogenerate -m "Your migration name"
alembic upgrade head
```

### Check Code Quality
```bash
black app/ tests/
flake8 app/ tests/
```

### View Logs
```bash
docker-compose logs -f app
```

### Stop Everything
```bash
docker-compose down
```

## 📊 Project Stats

- **Lines of Code**: ~12,000
- **Files**: 120+
- **Quality Score**: 7.2/10
- **Test Coverage**: 25-35%
- **Critical Issues**: 3 identified, 2 fixed

## 🎯 What's Been Done Recently

✅ Migration 004: Added 7 performance indexes  
✅ Analytics: Replaced mock data with real SQL queries  
✅ Docs: Consolidated into main README.md + archive/  
✅ Audit: Comprehensive code quality report generated  

## ❓ Need Help?

1. Check the [README.md](../README.md) - it has everything
2. Run `docker-compose logs app` to see errors
3. Look at existing endpoints in `app/api/v1/endpoints/`
4. Check `.env.example` for configuration options

---

**Happy coding!** 🚀
