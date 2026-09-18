# RAPPORT RCA - BARROW.AI Backend Database Connection Issue

## 📋 **Résumé Exécutif**

**Date:** 7 mai 2026  
**Problème:** Erreur `InterfaceError: cannot call PreparedStatement.fetch(): the underlying connection is closed`  
**Impact:** Échec des opérations d'écriture en base de données lors de requêtes WhatsApp concurrentes  
**Cause Racine:** Session SQLAlchemy partagée non thread-safe utilisée simultanément par plusieurs tâches asynchrones  
**Solution:** Implémenter des sessions par opération plutôt qu'une session partagée globale  

---

## 🎯 **Analyse du Problème**

### **1. Symptômes Observés**

```
sqlalchemy.dialects.postgresql.asyncpg.InterfaceError: cannot call PreparedStatement.fetch(): the underlying connection is closed
[SQL: INSERT INTO sessions (id, channel, external_id, language, user_agent, ip_address, is_active, opted_out, message_count, created_at, last_active, closed_at) VALUES ($1::UUID, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::VARCHAR, $6, $7::BOOLEAN, $8::BOOLEAN, $9::INTEGER, $10::TIMESTAMP WITH TIME ZONE, $11::TIMESTAMP WITH TIME ZONE, $12::TIMESTAMP WITH TIME ZONE)]
```

**Localisation:** `session_repository.py:97` dans `create_session()`  
**Contexte:** Opérations d'écriture concurrentes sur la table `sessions`  
**Fréquence:** Seulement lors de requêtes WhatsApp simultanées  

### **2. Analyse des Logs**

#### **Logs Normaux (Fonctionnement Correct)**
```
2026-05-07T11:28:54.233800Z [info     ] 🔍 _ensure_initialized: instance=126562686308368, class_initialized=True
2026-05-07T11:28:54.233960Z [info     ] ✅ Reusing shared services (instance=126562686308368)
2026-05-07T11:28:54.234124Z [debug    ] message_validation_passed
```

#### **Logs d'Erreur (Problème)**
```
2026-05-07T11:28:54.236176Z [debug    ] database_connection_closed     connection_id=126562686225984
2026-05-07T11:28:54.236979Z [debug    ] database_connection_checked_in connection_id=126562988330288
2026-05-07T11:28:54.237739Z [error    ] chat_service_unexpected_error
```

### **3. Pattern d'Occurrence**

- ✅ **Singleton RAG/ChatService:** Fonctionne parfaitement
- ✅ **Validation des messages:** Passe toujours
- ❌ **Connexions DB:** Fermées prématurément
- ❌ **Opérations d'écriture:** Échouent systématiquement

---

## 🔍 **Cause Racine Identifiée**

### **Architecture Actuelle (Défaillante)**

```python
# main.py - Session partagée globale
shared_session = await async_session_factory()
session_repo = SessionRepository(shared_session)

# whatsapp.py - Tâches background concurrentes
background_tasks.add_task(whatsapp_service.process_webhook, ...)
```

### **Problème Technique**

1. **Session SQLAlchemy Partagée:** Une seule session créée au démarrage
2. **Utilisation Concurrente:** Plusieurs webhooks simultanés utilisent la même session
3. **Non Thread-Safe:** SQLAlchemy async n'est pas conçu pour partager des sessions entre tâches concurrentes
4. **Fermeture Prématurée:** Une tâche ferme la connexion pendant qu'une autre l'utilise

### **Schéma du Problème**

```
┌─────────────────┐    ┌─────────────────┐
│   Webhook #1    │    │   Webhook #2    │
│                 │    │                 │
│ session.add()   │    │ session.add()   │ ← Concurrent access
│ session.flush() │    │ session.flush() │ ← Connection closed by #1
└─────────────────┘    └─────────────────┘
         │                       │
         └────── Connection ─────┘
                Closed ❌
```

---

## 📊 **Impact Métier**

### **Criticité**
- 🔴 **Forte:** Les utilisateurs WhatsApp ne peuvent pas créer de sessions
- 🔴 **Blocante:** Empêche l'onboarding des nouveaux utilisateurs
- 🟡 **Partielle:** Les utilisateurs existants peuvent continuer à chatter

### **Métriques Affectées**
- **Taux de Conversion:** Nouveaux utilisateurs bloqués
- **Satisfaction Utilisateur:** Erreurs 500 sur les premiers messages
- **Performance:** Pas d'impact sur les utilisateurs existants

---

## 💡 **Solutions Proposées**

### **Solution #1: Sessions par Opération (Recommandée)**

```python
# Dans les repositories - créer une session par opération
async def _get_session(self) -> AsyncSession:
    """Create a new session for each operation."""
    from app.core.database import async_session_factory
    return await async_session_factory()
```

**Avantages:**
- ✅ Thread-safe par conception
- ✅ Isolation parfaite entre opérations
- ✅ Gestion automatique des connexions
- ✅ Pas de partage d'état

**Inconvénients:**
- ⚠️ Overhead légèrement supérieur (création de session)
- ⚠️ Changement architectural important

### **Solution #2: Pool de Sessions**

```python
# Pool de sessions pré-allouées
_session_pool: asyncio.Queue[AsyncSession] = asyncio.Queue()

async def get_session_from_pool() -> AsyncSession:
    return await _session_pool.get()
```

**Avantages:**
- ✅ Thread-safe
- ✅ Performance optimisée

**Inconvénients:**
- ❌ Complexité de gestion du pool
- ❌ Risque de fuites de sessions

### **Solution #3: Mutex Global (Temporaire)**

```python
# Mutex global pour les opérations DB
_db_lock = asyncio.Lock()

async with _db_lock:
    # Toutes les opérations DB sérialisées
    session = await self._get_session()
    # ... opération ...
```

**Avantages:**
- ✅ Fix rapide
- ✅ Pas de changement architectural

**Inconvénients:**
- ❌ Performance dégradée
- ❌ Scalabilité limitée

---

## 🛠️ **Plan de Correction**

### **Phase 1: Fix Immédiat (Solution #3)**
1. Ajouter un mutex global pour les opérations DB
2. Tester en production
3. Monitorer les performances

### **Phase 2: Refactorisation (Solution #1)**
1. Modifier tous les repositories pour créer des sessions par opération
2. Supprimer la session partagée globale
3. Tests d'intégration complets

### **Phase 3: Optimisation**
1. Implémenter un cache de connexions si nécessaire
2. Optimiser les paramètres du pool de connexions

---

## 📈 **Métriques de Succès**

### **Fonctionnelles**
- ✅ 0 erreurs `InterfaceError` en production
- ✅ Création de sessions réussie pour nouveaux utilisateurs
- ✅ Taux de conversion des utilisateurs WhatsApp > 95%

### **Techniques**
- ✅ Latence moyenne des webhooks < 500ms
- ✅ Taux d'erreur des opérations DB < 0.1%
- ✅ Utilisation CPU/memoria acceptable

### **Observabilité**
- ✅ Logs détaillés pour debugging futur
- ✅ Métriques de performance des DB
- ✅ Alertes sur les erreurs de connexion

---

## 🎯 **Recommandations**

### **Immédiat (24h)**
1. **Implémenter Solution #3** (mutex) pour stabiliser la production
2. **Ajouter monitoring** des erreurs DB
3. **Communiquer** avec l'équipe produit

### **Court Terme (1 semaine)**
1. **Implémenter Solution #1** (sessions par opération)
2. **Tests de charge** avec scénarios de concurrence
3. **Migration progressive** en production

### **Long Terme (1 mois)**
1. **Refactorisation complète** de la couche DB
2. **Documentation** des patterns de session
3. **Formation équipe** sur les bonnes pratiques async DB

---

## 📋 **Risques et Mitigation**

### **Risques Identifiés**
- **Performance:** Dégradation avec mutex global
- **Complexité:** Changement architectural majeur
- **Régression:** Risque d'introduire de nouveaux bugs

### **Plans de Mitigation**
- **Tests exhaustifs** avant déploiement
- **Rollback plan** prêt
- **Monitoring continu** post-déploiement
- **Feature flags** pour contrôle des changements

---

## 📝 **Conclusion**

La cause racine est clairement identifiée : **une session SQLAlchemy partagée utilisée simultanément par plusieurs tâches asynchrones**. 

La solution recommandée est d'implémenter des **sessions par opération** dans les repositories, éliminant complètement le problème de concurrence.

Le singleton des services applicatifs fonctionne parfaitement - seul le pattern de session DB doit être corrigé.

**Priorité:** CRITIQUE - Bloque l'onboarding des nouveaux utilisateurs WhatsApp.