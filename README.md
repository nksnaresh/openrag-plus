# OpenRAG+ Platform

Reasoning-Augmented Generation (RAG+) Platform engineered for enterprise environments. OpenRAG+ transcends traditional retrieval by implementing multi-step reasoning, verifiable citations, and scalable serverless execution.

## Architecture (Phase 1 MVP)
- **Frontend**: Next.js App Router providing a modern chat workspace with reasoning traces.
- **API Router**: FastAPI serving as a lightweight REST gateway with JWT Authentication.
- **Database**: PostgreSQL with `pgvector` for unified structured and unstructured data retrieval.
- **Serverless Reasoning**: AWS Lambda running autonomous `Retrieve -> Reason (Chain of Thought) -> Verify` cycles via LangGraph.
- **Async Ingestion**: Documents uploaded seamlessly to AWS S3 trigger SQS events, spinning up dedicated Lambda workers to extract, chunk, and embed vector text securely without locking the API tier.

## Repository Structure
- `/frontend`: Next.js web application.
- `/backend`: FastAPI service and database definitions.
- `/serverless`: AWS SAM Infrastructure-as-Code definitions (`template.yaml`) and Python Lambda scripts for `ingestion` and `reasoning`.
- `docker-compose.yml`: For deploying the local PostgreSQL + `pgvector` database testing environment.
- `.github/workflows`: Automated CI/CD pipeline integrated with AWS SAM target deployments.

## Getting Started Locally

### 1. Database Setup
Make sure Docker is running on your machine:
```bash
docker-compose up -d
```

### 2. Backend API
Install dependencies and run the FastAPI server:
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend UI
Install packages and boot the Next.js development server:
```bash
cd frontend
npm install
npm run dev
```

### 4. Serverless Worker Simulation
You can utilize the AWS SAM CLI to mimic AWS lambda functionality locally without manual deployment:
```bash
cd serverless
sam build
# Test inference
sam local invoke ReasoningEngineFunction --event event.json
```

## Deployment
Deployments are completely automated via GitHub Actions (`.github/workflows/serverless-deploy.yml`). Pushing commits into the `main` branch automatically triggers the AWS SAM build and CloudFormation deployment covering the RAG+ serverless computing tier.
