# Guide d Adaptation Multi-Entreprise

> **Version :** 1.0.0 | **Mis a jour :** Aout 2026
> Ce guide explique comment deployer ce bot pour une nouvelle entreprise en modifiant uniquement 2 fichiers.

---

## Principe : Zero Code, Juste de la Configuration

Le bot est concu pour etre **totalement agnostique** de l identite de l entreprise.
Tout le contenu metier (nom, prompts, reponses, langues) est centralise dans un seul fichier YAML.

```
company.yaml          <- Identite de l entreprise (nom, prompts, reponses)
.env                  <- Secrets + infra (URL base de donnees, cles API)
```

**Changer d entreprise = modifier ces 2 fichiers + reinitialiser la base de connaissances.**
Aucun fichier Python ne doit etre touche.

---

## Etape 1 : Modifier `company.yaml`

C est le fichier le plus important. Il contient toute l identite du bot.

### 1.1 Informations de base

```yaml
company:
  name: "VOTRE_ENTREPRISE"          # Nom affiche dans les reponses
  bot_name: "VotreBot"              # Nom du bot
  tagline: "Votre slogan ici."      # Slogan (optionnel, laissez "" si aucun)
  website: "https://www.votre-site.com"
  support_email: "support@votre-site.com"
  support_phone: "+221 XX XXX XX XX"  # Optionnel
```

### 1.2 Langues supportees

```yaml
languages:
  supported:
    - "en"    # Anglais
    - "fr"    # Francais
    # Ajouter d autres langues si besoin (ex: "ar" pour l arabe)
  default: "fr"   # Langue par defaut si non detectee
```

> Le bot repondra automatiquement dans la langue de l utilisateur
> parmi celles listees ici. Si la langue detectee n est pas dans
> la liste, il utilisera la langue par defaut.

### 1.3 Prompts LLM (le coeur de la personnalite)

C est ici que vous definissez comment le bot "pense" et repond.
Ecrivez un prompt par langue. Les variables disponibles sont :
- `{bot_name}` : nom du bot
- `{company_name}` : nom de l entreprise
- `{context}` : documents RAG recuperes (NE PAS SUPPRIMER)
- `{history}` : historique de conversation (NE PAS SUPPRIMER)
- `{question}` : question de l utilisateur (NE PAS SUPPRIMER)

```yaml
prompt:
  fr: |
    Tu es {bot_name}, l assistant IA professionnel de {company_name}.
    {company_name} est [DECRIVEZ ICI CE QUE FAIT VOTRE ENTREPRISE].

    PERSONNALITE :
    - [Ton souhaite : formel, amical, technique, commercial...]
    - Expert en [domaine metier de votre entreprise]

    REGLES :
    1. Base tes reponses sur les documents du CONTEXTE si disponibles
    2. Si tu ne sais pas, dis-le et propose de contacter le support
    3. Sois concis (max 3-4 paragraphes)
    4. N invente jamais d informations

    CONTEXTE : {context}
    HISTORIQUE : {history}
    QUESTION : {question}
    REPONSE :

  en: |
    You are {bot_name}, the AI assistant for {company_name}.
    [English version of the prompt above]
    ...
    CONTEXT: {context}
    HISTORY: {history}
    QUESTION: {question}
    ANSWER:
```

> **Conseil prompt :** Soyez specifique sur le secteur d activite,
> le ton, et les limites du bot. Plus le prompt est precis,
> meilleure sera la qualite des reponses.

### 1.4 Reponses pre-construites

Ces reponses sont utilisees pour les cas simples (salutation, aide, arret)
SANS passer par le LLM. Elles sont instantanees et ne coutent rien en tokens.

Variables disponibles : `{bot_name}`, `{company_name}`, `{website}`, `{support_email}`

```yaml
responses:
  greeting:          # Declenchee par : hello, bonjour, hi, salut
    fr: "Bonjour ! Bienvenue chez {company_name}. Je suis {bot_name}..."
    en: "Hello! Welcome to {company_name}. I am {bot_name}..."

  help:              # Declenchee par : help, aide, menu
    fr: |
      Je suis {bot_name}, l assistant de {company_name}.
      Je peux vous aider avec :
      - [Service 1]
      - [Service 2]
      - [Service 3]
    en: |
      I am {bot_name}, the assistant for {company_name}.
      I can help you with:
      - [Service 1]
      ...

  fallback:          # Quand le RAG ne trouve rien de pertinent
    fr: "Je n ai pas d information sur ce sujet. Contactez {support_email} ou visitez {website}."
    en: "I don't have information on that. Contact {support_email} or visit {website}."

  stop:              # Declenchee par : STOP, unsubscribe
    fr: "Vous avez ete desabonne. Envoyez START pour vous reabonner."
    en: "You have been unsubscribed. Send START to resubscribe."

  start:             # Declenchee par : START, subscribe
    fr: "Bon retour ! Comment puis-je vous aider ?"
    en: "Welcome back! How can I help you?"

  error:             # Erreur technique interne
    fr: "Je rencontre un probleme technique. Veuillez reessayer dans quelques instants."
    en: "I am experiencing a technical issue. Please try again in a moment."

  hostile:           # Message inapproprie ou offensant
    fr: "Je suis la pour vous aider avec les services {company_name}."
    en: "I am here to help with {company_name} services."
```

---

## Etape 2 : Modifier `.env`

Ne touchez qu aux variables suivantes (les autres sont infra) :

```bash
# Nom de l application (apparait dans les logs)
APP_NAME=VOTRE_ENTREPRISE Bot

# Collection Qdrant — DOIT etre unique par entreprise
# Format recommande : [nom_entreprise]_knowledge_v1
QDRANT_COLLECTION=votre_entreprise_knowledge_v1

# Domaine de production
CORS_ORIGINS=["https://votre-domaine.com","https://admin.votre-domaine.com"]

# Modele LLM (gemini-2.5-flash-lite est le modele generique recommande)
GEMINI_MODEL=gemini-2.5-flash-lite

# Chemin vers le fichier company.yaml (optionnel, defaut : company.yaml)
COMPANY_CONFIG_PATH=company.yaml
```

> Ne modifiez PAS les secrets (JWT_SECRET, ENCRYPTION_KEY, etc.)
> si vous reutilisez la meme installation.
> Si c est une nouvelle installation, regenerez-les (voir Etape 5).

---

## Etape 3 : Reinitialiser la base de connaissances

La base vectorielle Qdrant contient les documents de l ancienne entreprise.
Il faut la vider et y indexer les nouveaux documents.

### 3.1 Sur le serveur

```bash
# Connexion au serveur
ssh user@votre-serveur.com
cd /opt/votre-projet

# 1. Vider l ancienne collection Qdrant
docker compose exec qdrant sh -c \
  'curl -X DELETE http://localhost:6333/collections/$QDRANT_COLLECTION'

# 2. Vider la table PostgreSQL des documents
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "DELETE FROM knowledge_docs; DELETE FROM audit_logs WHERE action = 'KNOWLEDGE_UPLOAD';"

# 3. Vider le cache Redis (reponses mises en cache de l ancienne entreprise)
docker compose exec redis redis-cli FLUSHDB
```

### 3.2 Redemarrer les services

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

### 3.3 Uploader les nouveaux documents

Via l interface d administration (`https://admin.votre-domaine.com`) :

1. Connectez-vous avec un compte admin
2. Allez dans **Knowledge Base > Upload**
3. Uploadez vos documents au format PDF, DOCX, ou TXT
4. Attendez que le statut passe a **ACTIVE** (indexation automatique)

**Documents recommandes a preparer :**
- Catalogue de produits/services
- FAQ clients
- Conditions generales / SLA
- Presentation de l entreprise
- Guides d utilisation
- Tarifs (si autorises)
- Contacts et emplacements

> Plus la base de connaissances est complete et bien redigee,
> plus les reponses du bot seront precises et utiles.

---

## Etape 4 : Tester

### Test rapide via l API

```bash
# Test d une question basique
curl -X POST https://votre-domaine.com/api/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour", "language": "fr"}'

# Verification de la sante
curl https://votre-domaine.com/health/live
```

### Checklist de validation

- [ ] Le bot repond "Bonjour" avec le nom de la nouvelle entreprise
- [ ] Le bot repond a une question sur l entreprise en utilisant les documents uploades
- [ ] Le bot repond "Je n ai pas d information" quand il ne sait pas
- [ ] Aucune mention de l ancienne entreprise dans les reponses
- [ ] Les langues configurees fonctionnent (tester EN et FR)
- [ ] WhatsApp repond correctement (si configure)

---

## Etape 5 : Nouvelle installation from scratch

Si vous deployez sur un nouveau serveur (pas de reutilisation) :

### 5.1 Cloner et configurer

```bash
git clone https://github.com/laurentmd5/bai-backend.git mon-bot-entreprise
cd mon-bot-entreprise

# Creer le .env a partir de l exemple
cp .env.example .env
nano .env
```

### 5.2 Generer les secrets

```bash
# JWT Secret (256 bits)
openssl rand -hex 32

# JWT Refresh Secret
openssl rand -hex 32

# Encryption Key (AES-256, DOIT etre exactement 32 bytes base64)
openssl rand -base64 32

# CSRF Secret
openssl rand -hex 32

# WhatsApp App Secret (fourni par Meta)
# -> Copier depuis Meta Developer Console
```

### 5.3 Remplir le .env complet

```bash
# Application
APP_NAME=VOTRE_ENTREPRISE Bot
APP_VERSION=1.0.0
ENVIRONMENT=production

# Secrets (generes a l etape precedente)
JWT_SECRET=[votre_jwt_secret]
JWT_REFRESH_SECRET=[votre_refresh_secret]
ENCRYPTION_KEY=[votre_encryption_key]
CSRF_SECRET=[votre_csrf_secret]

# Base de donnees
POSTGRES_USER=botuser
POSTGRES_PASSWORD=[mot_de_passe_fort]
POSTGRES_DB=bot_db

# Redis
REDIS_PASSWORD=[mot_de_passe_fort]

# RabbitMQ
RABBITMQ_USER=botuser
RABBITMQ_PASSWORD=[mot_de_passe_fort]

# LLM
GEMINI_API_KEY=[votre_cle_gemini]
GEMINI_MODEL=gemini-2.5-flash-lite

# Qdrant
QDRANT_COLLECTION=votre_entreprise_knowledge_v1
QDRANT_SIMILARITY_THRESHOLD=0.70

# WhatsApp (optionnel)
WHATSAPP_VERIFY_TOKEN=[token_de_verification]
WHATSAPP_ACCESS_TOKEN=[token_acces_meta]
WHATSAPP_PHONE_NUMBER_ID=[id_numero_whatsapp]

# CORS
CORS_ORIGINS=["https://votre-domaine.com"]
```

### 5.4 Lancer

```bash
docker compose up -d

# Verifier que tout demarre
docker compose logs -f --tail=50
```

### 5.5 Creer le premier admin

```bash
# Via l API (une seule fois)
curl -X POST https://localhost:8000/api/v1/admin/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@votre-entreprise.com",
    "password": "[mot_de_passe_fort]",
    "full_name": "Admin VOTRE_ENTREPRISE"
  }'
```

---

## Reference : Variables de Template

| Variable | Description | Exemple |
|----------|-------------|---------|
| `{company_name}` | Nom de l entreprise | `NETSYSTEME` |
| `{bot_name}` | Nom du bot | `NetBot` |
| `{website}` | Site web | `https://www.netsysteme.sn` |
| `{support_email}` | Email support | `support@netsysteme.sn` |
| `{context}` | Documents RAG (NE PAS SUPPRIMER dans les prompts) | *(contenu automatique)* |
| `{history}` | Historique conversation (NE PAS SUPPRIMER) | *(contenu automatique)* |
| `{question}` | Question utilisateur (NE PAS SUPPRIMER) | *(contenu automatique)* |

---

## Reference : Intents Reconnus

Ces mots-cles declenchent des reponses instantanees sans passer par le LLM :

| Intent | Mots-cles | Reponse utilisee |
|--------|-----------|-----------------|
| Salutation | hello, hi, bonjour, salut, hey | `responses.greeting` |
| Aide | help, aide, menu, capabilities | `responses.help` |
| Merci | thank, merci, thanks | *(LLM gere naturellement)* |
| Desinscription | stop, unsubscribe, opt-out | `responses.stop` |
| Reabonnement | start, subscribe, opt-in | `responses.start` |
| Statut | status, ping, test | Message operationnel |

---

## Exemples de company.yaml par Secteur

### Banque / Finance

```yaml
company:
  name: "MA BANQUE"
  bot_name: "BankBot"
  tagline: "Votre banque, toujours disponible."

prompt:
  fr: |
    Tu es {bot_name}, l assistant virtuel de {company_name}.
    {company_name} est une banque offrant des services de credit,
    epargne, transfert d argent et banque mobile.

    REGLES IMPORTANTES :
    - Ne donne JAMAIS de conseils financiers specifiques
    - Pour toute operation sur un compte, oriente vers une agence
    - Base toutes tes reponses sur les documents officiels
    - N invente jamais de taux, de frais ou de conditions

    CONTEXTE : {context}
    HISTORIQUE : {history}
    QUESTION : {question}
    REPONSE :
```

### Sante / Clinique

```yaml
company:
  name: "CLINIQUE SANTE PLUS"
  bot_name: "SanteBot"
  tagline: "Votre sante, notre priorite."

prompt:
  fr: |
    Tu es {bot_name}, l assistant de {company_name}.

    REGLES CRITIQUES :
    - Tu n es PAS un medecin et ne donnes JAMAIS de diagnostic
    - Pour toute urgence medicale, oriente immediatement vers le 15 (SAMU)
    - Tu peux informer sur les services, horaires, et prise de RDV
    - Base tes reponses sur les documents de la clinique uniquement

    CONTEXTE : {context}
    HISTORIQUE : {history}
    QUESTION : {question}
    REPONSE :
```

### E-commerce / Boutique

```yaml
company:
  name: "MA BOUTIQUE"
  bot_name: "ShopBot"
  tagline: "Livraison rapide, satisfaction garantie."

prompt:
  fr: |
    Tu es {bot_name}, l assistant de {company_name}.
    Tu aides les clients avec leurs commandes, produits, livraisons et retours.

    TU PEUX :
    - Informer sur les produits disponibles et leurs caracteristiques
    - Expliquer les delais et frais de livraison
    - Guider sur la politique de retour
    - Orienter vers le support pour les problemes de commande

    TU NE PEUX PAS :
    - Creer ou modifier des commandes directement
    - Promettre des prix ou remises non documentes

    CONTEXTE : {context}
    HISTORIQUE : {history}
    QUESTION : {question}
    REPONSE :
```

---

## Troubleshooting

### Le bot repond encore avec l ancienne identite

```bash
# 1. Verifier que company.yaml est bien monte dans le container
docker compose exec backend cat /app/company.yaml

# 2. Redemarrer le backend pour recharger le singleton
docker compose restart backend worker

# 3. Vider le cache Redis (les reponses mises en cache peuvent etre anciennes)
docker compose exec redis redis-cli FLUSHDB
```

### Le bot repond "Je n ai pas d information" sur tout

```bash
# 1. Verifier que des documents sont indexes
curl http://localhost:8000/api/v1/admin/knowledge \
  -H "Authorization: Bearer [votre_token]"

# 2. Verifier la collection Qdrant
curl http://localhost:6333/collections/$QDRANT_COLLECTION

# 3. Baisser le seuil de similarite dans .env
QDRANT_SIMILARITY_THRESHOLD=0.40
```

### Le bot ne comprend pas la langue configuree

```bash
# 1. Verifier company.yaml
cat company.yaml | grep -A 5 "languages:"

# 2. Le bot detect automatiquement la langue mais utilise la langue
#    par defaut si non reconnue.
#    Assurez-vous que "default" est correctement configure.
```
