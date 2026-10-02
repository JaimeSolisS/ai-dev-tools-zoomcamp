# Archboard

A browser-based whiteboard for live system-design interviews. An interviewer creates a
session and shares a link; candidates and other interviewers join and draw on the same
infinite canvas in real time: architecture components, connectors, labels, sticky notes
and freehand drawing. The canvas is saved automatically for review after the interview.

The product spec is in [`_docs/spec.md`](_docs/spec.md) and the API contract in
[`openapi.yaml`](openapi.yaml).

## Stack

| Part                     | Tech                                                  | Docs                                     |
|--------------------------|-------------------------------------------------------|------------------------------------------|
| [`frontend/`](frontend)  | React 18, TypeScript, Vite, Vitest                    | [frontend/README.md](frontend/README.md) |
| [`backend/`](backend)    | FastAPI, SQLAlchemy (SQLite or Postgres), WebSockets  | [backend/README.md](backend/README.md)   |
| [`e2e/`](e2e)            | Playwright, run against docker compose                |                                          |
| [`terraform/`](terraform)| AWS: one EC2 instance running the app and Postgres     | [below](#deploy-to-aws)                  |

In production one container serves both: the backend serves the built frontend at `/`
and the API at `/v1`. Real-time updates go over a WebSocket from the same server.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and Node 22 for local development, and Docker
for the container setups.

```bash
make install   # npm install + uv sync
make dev       # backend on :8091, frontend on http://localhost:5173
```

Or run everything in containers, with Postgres:

```bash
docker compose up --build   # http://localhost:8091
```

Run `make help` to list every target.

### Signing in

Out of the box the backend runs in **dev mode** (`ARCHBOARD_DEV=true`). It sends no email:
the magic-link token comes back in the API response, so any email address can sign in.
An empty database also gets demo accounts (`ada@example.com` and `grace@example.com`,
password `password123`) and sample sessions. See [backend/README.md](backend/README.md)
for the demo data and every setting.

## Tests

| Command                      | What it runs                                                  |
|------------------------------|---------------------------------------------------------------|
| `make test`                  | Backend (pytest) and frontend (Vitest) unit tests             |
| `make test-backend-postgres` | Backend tests against a throwaway Postgres container         |
| `make test-integration`      | The frontend's HTTP client against a running backend          |
| `make test-compose`          | Builds the docker compose stack and tests it over HTTP        |
| `make e2e`                   | Playwright browser tests against the docker compose stack     |
| `make lint`                  | Frontend type check, backend ruff lint and format check       |

## Deploy to AWS

[`terraform/`](terraform) runs the app on one `t3.nano` EC2 instance (us-east-1, AWS profile
`jsolisdev`). Docker compose on the instance runs the app image and Postgres, with the
database stored on the instance's disk. The image is built on your machine and pushed to ECR,
because the instance is too small to build the frontend itself.

```bash
make deploy                          # terraform apply, build and push the image, restart the app
make deploy-app                      # code-only redeploy (skips terraform apply)
make destroy                         # delete all the AWS resources, database included (asks first)
terraform -chdir=terraform output    # URL, instance id, ECR repository
```

The targets use the `jsolisdev` AWS profile; override it with `make deploy AWS_PROFILE=other`.
Terraform state is kept in S3 (bucket `archboard-tfstate-<account>`, with locking), so
local runs and the pipeline share it; plain `terraform` commands need `AWS_PROFILE` set.

There is no SSH; open a shell on the instance with Session Manager:

```bash
aws ssm start-session --profile jsolisdev --region us-east-1 \
  --target "$(terraform -chdir=terraform output -raw instance_id)"
```

Things to know before sharing the deployment:

- It still runs in **dev mode**, so anyone who can reach the URL can sign in as any email.
- It is served over plain **HTTP** on the instance's public IP; there is no domain or TLS.
- `make destroy` deletes the instance, and with it the Postgres data.

### CI/CD

[`.github/workflows/archboard.yml`](../../.github/workflows/archboard.yml) runs on every push
and pull request that touches this folder:

1. **Backend** (ruff + pytest) and **frontend** (type check + Vitest) tests, in parallel.
2. **Integration**: builds the docker compose stack, then runs the compose integration tests,
   the frontend HTTP client tests and the Playwright e2e tests against it.
3. **Deploy** (pushes to `main` only): assumes an AWS role through GitHub OIDC (no stored
   keys), runs `terraform apply`, builds and pushes the image tagged with the commit, rolls it
   out over SSM, and waits until `GET /health` reports the database is up and the new commit
   is the one running.

The OIDC provider, the deploy role and the state bucket live in
[`terraform/bootstrap/`](terraform/bootstrap). They are applied once by hand with
`make bootstrap`, so the pipeline's role can't widen its own permissions.

`GET /health` returns `{"status", "database", "version"}`, and 503 when the database is unreachable.

## Layout

```
frontend/      React app (canvas, room, dashboard, services layer)
backend/       FastAPI app, unit tests, docker compose integration tests
e2e/           Playwright browser tests
terraform/     AWS deployment (EC2 + ECR), deploy scripts, bootstrap/ for CI access
_docs/         product and technical spec
openapi.yaml   API contract shared by frontend and backend
Dockerfile     one image: built frontend served by the backend
docker-compose.yaml   app + Postgres
```
