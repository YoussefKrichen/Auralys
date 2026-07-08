# Plan de déploiement exact de `auralys` sur GCP

## Objectif

Déployer `auralys` sur Google Cloud Platform avec une architecture simple, stable et adaptée à une prod légère ou moyenne.

## Architecture recommandée

- `Frontend + Backend FastAPI` sur **Cloud Run**
- `PostgreSQL` sur **Cloud SQL for PostgreSQL**
- `Qdrant` sur **Compute Engine**
- images Docker dans **Artifact Registry**
- secrets dans **Secret Manager**
- accès privé du backend vers `Qdrant` via **VPC**

## Pourquoi cette architecture

- **Cloud Run** est adapté au backend HTTP stateless
- **Cloud SQL** remplace proprement le conteneur PostgreSQL
- **Qdrant** est stateful, donc plus adapté à une VM qu’à Cloud Run
- **Artifact Registry** est la solution standard pour stocker les images Docker
- **Secret Manager** évite de mettre les clés directement dans `.env`

## Schéma logique

```text
Utilisateur
   |
   v
Cloud Run (FastAPI + frontend dist)
   | \
   |  \
   |   -> Cloud SQL (PostgreSQL)
   |
   -> Qdrant sur VM Compute Engine
```

## 1. Services à créer

### 1.1 Cloud Run

Nom conseillé :
- `auralys-api`

Rôle :
- sert l’API FastAPI
- peut aussi servir `frontend/dist`

Commande d’exécution dans le conteneur :

```bash
python -m app.main serve --host 0.0.0.0 --port 8000
```

### 1.2 Cloud SQL

Nom conseillé :
- `auralys-postgres`

Paramètres :
- moteur : `PostgreSQL`
- base : `auralys`
- utilisateur : `auralys`

### 1.3 Compute Engine

Nom conseillé :
- `auralys-qdrant`

Rôle :
- héberge le conteneur `qdrant/qdrant:v1.13.4`
- stockage persistant pour la base vectorielle

### 1.4 Artifact Registry

Nom conseillé :
- `auralys`

Type :
- `Docker`

### 1.5 Secret Manager

Secrets à stocker :
- `GOOGLE_API_KEY`
- `POSTGRES_DSN`
- `GROQ_API_KEY` si utilisé
- `LANGSMITH_API_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `FACEBOOK_OAUTH_CLIENT_ID`
- `FACEBOOK_OAUTH_CLIENT_SECRET`

## 2. APIs GCP à activer

Activer au minimum :

- `Cloud Run Admin API`
- `Artifact Registry API`
- `Cloud Build API`
- `Cloud SQL Admin API`
- `Secret Manager API`
- `Compute Engine API`
- `VPC Access API`

Commande type :

```bash
gcloud services enable run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  vpcaccess.googleapis.com
```

## 3. Variables d’environnement recommandées

### Backend Cloud Run

```env
APP_ENV=prod
LLM_PROVIDER=gemini
GEMINI_CHAT_MODEL=gemini-2.5-pro

POSTGRES_DSN=postgresql://auralys:PASSWORD@/auralys?host=/cloudsql/PROJECT_ID:REGION:auralys-postgres

QDRANT_URL=http://10.0.0.10:6333
QDRANT_COLLECTION=auralys_chunks

GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY

LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=YOUR_LANGSMITH_API_KEY
LANGSMITH_PROJECT=Auralys

BACKEND_PUBLIC_URL=https://YOUR_CLOUD_RUN_URL
FRONTEND_PUBLIC_URL=https://YOUR_CLOUD_RUN_URL
```

Notes :
- `POSTGRES_DSN` doit pointer vers `Cloud SQL`
- `QDRANT_URL` doit pointer vers l’IP privée ou interne de la VM Qdrant

## 4. Étapes exactes de déploiement

### 4.1 Créer le projet et choisir la région

Exemple :
- projet : `auralys-prod`
- région : `europe-west1`

Configurer :

```bash
gcloud config set project PROJECT_ID
gcloud config set run/region REGION
```

### 4.2 Créer le repository Artifact Registry

```bash
gcloud artifacts repositories create auralys \
  --repository-format=docker \
  --location=REGION \
  --description="Docker images for Auralys"
```

### 4.3 Auth Docker pour Artifact Registry

```bash
gcloud auth configure-docker REGION-docker.pkg.dev
```

### 4.4 Builder et pousser l’image

```bash
docker build -t REGION-docker.pkg.dev/PROJECT_ID/auralys/auralys-api:latest .
docker push REGION-docker.pkg.dev/PROJECT_ID/auralys/auralys-api:latest
```

## 5. Déployer PostgreSQL sur Cloud SQL

### 5.1 Créer l’instance

```bash
gcloud sql instances create auralys-postgres \
  --database-version=POSTGRES_15 \
  --cpu=1 \
  --memory=3840MiB \
  --region=REGION
```

### 5.2 Créer la base

```bash
gcloud sql databases create auralys \
  --instance=auralys-postgres
```

### 5.3 Créer l’utilisateur

```bash
gcloud sql users create auralys \
  --instance=auralys-postgres \
  --password=YOUR_PASSWORD
```

## 6. Déployer Qdrant sur Compute Engine

### 6.1 Créer la VM

Exemple :

```bash
gcloud compute instances create auralys-qdrant \
  --zone=REGION-b \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB
```

### 6.2 Se connecter à la VM

```bash
gcloud compute ssh auralys-qdrant --zone=REGION-b
```

### 6.3 Installer Docker sur la VM

Exemple rapide :

```bash
sudo apt update
sudo apt install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
```

### 6.4 Lancer Qdrant

```bash
sudo mkdir -p /opt/qdrant_storage

docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v /opt/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:v1.13.4
```

### 6.5 Ouvrir le port seulement au réseau utile

Configurer les règles firewall pour ne pas exposer Qdrant publiquement si possible.

## 7. Connecter Cloud Run au réseau privé

Créer un accès VPC pour que Cloud Run puisse joindre la VM Qdrant.

### 7.1 Créer le connecteur VPC

```bash
gcloud compute networks vpc-access connectors create auralys-connector \
  --region=REGION \
  --network=default \
  --range=10.8.0.0/28
```

## 8. Déployer Cloud Run

### 8.1 Déploiement de base

```bash
gcloud run deploy auralys-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/auralys/auralys-api:latest \
  --region REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8000
```

### 8.2 Déploiement avec Cloud SQL + VPC

```bash
gcloud run deploy auralys-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/auralys/auralys-api:latest \
  --region REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8000 \
  --add-cloudsql-instances PROJECT_ID:REGION:auralys-postgres \
  --vpc-connector auralys-connector \
  --set-env-vars APP_ENV=prod,LLM_PROVIDER=gemini,GEMINI_CHAT_MODEL=gemini-2.5-pro,QDRANT_URL=http://10.0.0.10:6333,QDRANT_COLLECTION=auralys_chunks
```

Ensuite ajouter les secrets :

```bash
gcloud run services update auralys-api \
  --region REGION \
  --update-secrets GOOGLE_API_KEY=GOOGLE_API_KEY:latest,LANGSMITH_API_KEY=LANGSMITH_API_KEY:latest
```

## 9. Initialiser la base et indexer les données

Après déploiement, il faut exécuter :

```bash
python -m app.main init-db
python -m app.main ingest
python -m app.main index
```

### Recommandation

Ne pas faire cela manuellement dans le service `Cloud Run`.

Faire plutôt :
- soit depuis une machine d’admin
- soit via **Cloud Run Jobs**
- soit via CI/CD

## 10. Vérifications

### 10.1 Vérifier l’API

```bash
curl https://YOUR_CLOUD_RUN_URL/health
```

Réponse attendue :

```json
{"status":"ok"}
```

### 10.2 Vérifier la config RAG

```bash
curl https://YOUR_CLOUD_RUN_URL/rag/status
```

### 10.3 Vérifier la DB vectorielle

Depuis le backend, `QDRANT_URL` doit être joignable.

## 11. Dimensionnement initial recommandé

### Cloud Run

- CPU : `1`
- RAM : `1Gi` à `2Gi`
- min instances :
  - `0` en dev
  - `1` si tu veux éviter le cold start

### Cloud SQL

- petite instance au départ
- augmenter selon charge et volume

### Qdrant VM

- `e2-small` ou mieux si beaucoup d’embeddings
- SSD persistant

## 12. Coût recommandé

### Architecture recommandée pour commencer

- `Cloud Run`
- `Cloud SQL`
- `Qdrant sur VM`

### À éviter au début

- `GKE`

Pourquoi :
- plus complexe
- plus cher
- inutile pour `auralys` tant que la charge reste modérée

## 13. Ordre de mise en production

1. créer projet GCP
2. activer APIs
3. créer Artifact Registry
4. builder/pusher l’image
5. créer Cloud SQL
6. créer VM Qdrant
7. configurer VPC connector
8. déployer Cloud Run
9. initialiser DB
10. lancer `ingest`
11. lancer `index`
12. tester `health`, `rag/status`, upload image, conversation

## 14. Recommandation finale

### Phase 1

- Cloud Run
- Cloud SQL
- Qdrant sur VM

### Phase 2 si croissance

- migrer Qdrant vers GKE
- éventuellement séparer frontend et backend
- ajouter CI/CD complet

## 15. Résumé exécutif

Pour `auralys`, la meilleure architecture GCP est :

- **Cloud Run** pour l’app
- **Cloud SQL** pour PostgreSQL
- **Compute Engine** pour Qdrant

C’est la solution la plus pragmatique pour :
- déployer vite
- limiter les coûts
- garder une architecture propre
- pouvoir évoluer ensuite
