# Step — Deploy to Google Cloud Run

## Overview
Two Cloud Run services: backend (FastAPI/uvicorn) and frontend (Next.js standalone).
Backend deploys first. Frontend is built with the backend URL as a build arg.

Uploads are stored on Cloud Storage (GCS) and served via a signed-URL redirect — Cloud Run containers have ephemeral disks that reset on restart.

Secrets (API keys, firebase-key.json) live in Google Secret Manager and are mounted into the container at runtime.

---

## Prerequisites
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com
```

---

## Stage 1 — Create Artifact Registry repo and Secret Manager secrets

```bash
# Docker image registry
gcloud artifacts repositories create comply \
  --repository-format=docker \
  --location=europe-west2 \
  --description="COMPLY app images"

# Secrets
echo -n "YOUR_ANTHROPIC_KEY" | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
echo -n "YOUR_GOOGLE_API_KEY" | gcloud secrets create GOOGLE_API_KEY --data-file=-
gcloud secrets create FIREBASE_KEY --data-file=backend/firebase-key.json

# Allow Cloud Run's service account to access secrets
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
for secret in ANTHROPIC_API_KEY GOOGLE_API_KEY FIREBASE_KEY; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

### Confirm
`gcloud secrets list` shows all three secrets.

---

## Stage 2 — Create Cloud Storage bucket for uploads

```bash
gsutil mb -l europe-west2 gs://comply-uploads-YOUR_PROJECT_ID

# Allow the backend's service account to read/write
gsutil iam ch serviceAccount:$SA:roles/storage.objectAdmin gs://comply-uploads-YOUR_PROJECT_ID
```

### Note
The backend code currently saves files to a local `./uploads` directory and serves them via FastAPI `StaticFiles`. In Stage 5 the backend is updated to write to and serve from GCS instead.

---

## Stage 3 — Build and deploy the backend

```bash
REGION=europe-west2
PROJECT_ID=YOUR_PROJECT_ID
REGISTRY=$REGION-docker.pkg.dev/$PROJECT_ID/comply

# Build
docker build -t $REGISTRY/backend:latest ./backend
docker push $REGISTRY/backend:latest

# Deploy
gcloud run deploy comply-backend \
  --image=$REGISTRY/backend:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --port=8000 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --set-secrets="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest" \
  --set-secrets="/secrets/firebase-key.json=FIREBASE_KEY:latest" \
  --set-env-vars="GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-key.json,UPLOAD_DIR=/tmp/uploads,GCS_BUCKET=comply-uploads-$PROJECT_ID"
```

Note the URL output. It will look like:
`https://comply-backend-xxxx-nw.a.run.app`

### Confirm
```bash
curl https://comply-backend-xxxx-nw.a.run.app/files
# Should return [] (empty array, not a 500)
```

---

## Stage 4 — Build and deploy the frontend

```bash
BACKEND_URL=https://comply-backend-xxxx-nw.a.run.app   # from Stage 3

# Build with backend URL baked in
docker build \
  --build-arg NEXT_PUBLIC_API_URL=$BACKEND_URL \
  -t $REGISTRY/frontend:latest \
  ./frontend

docker push $REGISTRY/frontend:latest

# Deploy
gcloud run deploy comply-frontend \
  --image=$REGISTRY/frontend:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --port=3000 \
  --memory=512Mi \
  --cpu=1
```

Get the frontend URL (e.g. `https://comply-frontend-xxxx-nw.a.run.app`).

### Update backend CORS to allow frontend origin
```bash
gcloud run services update comply-backend \
  --region=$REGION \
  --update-env-vars="CORS_ORIGINS=https://comply-frontend-xxxx-nw.a.run.app"
```

### Confirm
Open the frontend URL. The app should load and uploads should reach the backend.

---

## Stage 5 — Update backend to use Cloud Storage for uploads

**Problem:** Cloud Run containers have ephemeral disks. Uploaded files are lost on container restart or scale-out.

**Fix:** Update `backend/main.py` to write uploads to GCS and redirect `/uploads/{fileId}` requests to a signed GCS URL (or make the bucket public).

Key changes in `main.py`:
```python
from google.cloud import storage as gcs_storage

GCS_BUCKET = os.getenv("GCS_BUCKET")
gcs_client = gcs_storage.Client() if GCS_BUCKET else None

# On upload: write to GCS instead of local disk
# blob = gcs_client.bucket(GCS_BUCKET).blob(file_id)
# blob.upload_from_file(file.file)

# /uploads/{fileId} endpoint: redirect to signed URL or public GCS URL
```

This is the only code change needed for true persistence. Until this is done, uploads persist only while the container instance is alive (works if `--min-instances=1` and traffic is steady).

---

## Verification Checklist

- [ ] `gcloud run services list` shows both `comply-backend` and `comply-frontend`
- [ ] Frontend URL loads the app
- [ ] Upload a PDF → appears in file list
- [ ] Click the file → PDF shows in centre panel
- [ ] Send a compliance chat message → streams back correctly
- [ ] Citation click → PDF navigates to correct page (once PDF viewer is restored)
- [ ] Backend URL returns 404 on `/` but `[]` on `/files` (health check)
