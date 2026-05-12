# infra/railway

Deployment manifests + Railway service config. To be filled in once the team
selects production env (currently scaffold).

Planned services:

| Service              | Type            | Build           |
|----------------------|-----------------|-----------------|
| `bal-api`            | Web service     | Nixpacks (uv)   |
| `bal-web`            | Static / SPA    | Nixpacks (pnpm) |
| `bal-inference`      | GPU service     | Dockerfile      |
| `bal-postgres`       | Managed Postgres | Railway addon   |
