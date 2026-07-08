# Auralys Backend

Premiere version locale du backend agentique Auralys pour Aromair.

## Stack

- FastAPI
- LangGraph
- PostgreSQL
- Qdrant
- Pydantic
- Docker Compose

## Architecture

Le backend expose 8 composants agentiques, tous modelises comme des nodes LangGraph :

1. `Coordinator Agent`
2. `SAV Agent`
3. `Client Agent`
4. `Diffuseur Agent`
5. `Technicien Agent`
6. `Documents Agent`
7. `Recommendation Agent`
8. `ReportLearning Agent`

Le `Coordinator Agent` :

- recoit la requete utilisateur
- classifie l'intention
- decide si le contexte doit venir de PostgreSQL, Qdrant ou des deux
- recupere le contexte
- selectionne les agents utiles
- laisse les agents produire leur analyse
- renvoie une reponse structuree

## Structure

```text
app/
  main.py
  api/routes.py
  core/config.py
  graph/state.py
  graph/graph_builder.py
  graph/router.py
  agents/
  rag/
  db/
  vectorstore/
  services/
tests/
docker-compose.yml
requirements.txt
.env.example
```

## Donnees et RAG

### PostgreSQL

Tables minimales :

- `clients`
- `diffuseurs`
- `techniciens`
- `interventions`
- `reclamations`
- `recommendations`

### Qdrant

Collections :

- `auralys_documents`
- `auralys_memory`

### Agentic RAG

- `PostgresRetriever` pour le contexte structure
- `QdrantRetriever` pour les documents et la memoire semantique
- `HybridRetriever` pour arbitrer entre les deux

## LLM et embeddings

Cette version utilise :

- un `MockLLMClient`
- un `FakeEmbeddingProvider`

Les interfaces restent remplacables pour brancher plus tard OpenAI, Gemini, Vertex AI ou un modele local.

## Endpoints

### `POST /api/auralys/invoke`

Exemple :

```json
{
  "user_query": "Le client 1 a une reclamation urgente sur son diffuseur",
  "client_id": 1,
  "diffuseur_id": 1
}
```

Reponse :

```json
{
  "request_type": "sav_analysis",
  "agents_used": ["Coordinator Agent", "SAV Agent"],
  "summary": "",
  "findings": [],
  "recommendations": [],
  "priority": "high",
  "requires_human_validation": true,
  "next_actions": [],
  "trace": []
}
```

### `GET /api/auralys/health`

Retourne l'etat FastAPI, PostgreSQL et Qdrant.

### `POST /api/auralys/documents/index`

Indexe une liste de documents dans `auralys_documents` ou `auralys_memory`.

### `POST /api/auralys/recommendations/validate`

Normalise les recommandations et determine si une validation humaine reste necessaire.

## Demarrage local

1. Copier `.env.example` vers `.env`
2. Lancer l'infra :

```bash
docker compose up -d
```

3. Installer les dependances :

```bash
pip install -r requirements.txt
```

4. Lancer l'API :

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Seed

Au demarrage, si `AURALYS_AUTO_SEED=true`, le backend :

- initialise le schema PostgreSQL
- cree les collections Qdrant
- injecte des donnees de demonstration

## Tests

Tests cibles :

```bash
pytest tests/test_graph.py tests/test_api.py
```

Les tests de connexion PostgreSQL et Qdrant sont marques comme `skip` si les services locaux ne sont pas disponibles.
