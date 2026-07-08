# Hostinger VPS Deployment

This project is ready to run on a Hostinger VPS with Docker.

## 1. Recommended Hostinger setup

- Choose a Linux VPS.
- Prefer the Docker-ready template if Hostinger offers it.
- Point your domain to the VPS IP.

## 2. Copy the project to the server

Example:

```bash
git clone <your-repo-url> auralys
cd auralys
```

## 3. Prepare environment

Create `.env` from the example:

```bash
cp deploy/hostinger.env.example .env
```

Update at least:

- `POSTGRES_PASSWORD`
- `GOOGLE_API_KEY`
- `BACKEND_PUBLIC_URL`
- `FRONTEND_PUBLIC_URL`
- OAuth variables if you use Google/Facebook login

## 4. Build and start containers

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 5. Load your data stores

After the containers are up:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.main ingest
docker compose -f docker-compose.prod.yml exec backend python -m app.main index
```

## 6. Access the app

- Frontend: `http://YOUR_SERVER_IP`
- API health: `http://YOUR_SERVER_IP/api/health`

If you bind a domain to the VPS and put SSL in front of it, use:

- ``

## 7. Useful commands

See logs:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f web
```

Restart:

```bash
docker compose -f docker-compose.prod.yml restart
```

Rebuild:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Stop:

```bash
docker compose -f docker-compose.prod.yml down
```

## 8. Notes

- The frontend is served by Nginx from the `web` container.
- `/api/*` is proxied internally to the FastAPI backend.
- Postgres and Qdrant are private inside Docker and are not exposed publicly.
