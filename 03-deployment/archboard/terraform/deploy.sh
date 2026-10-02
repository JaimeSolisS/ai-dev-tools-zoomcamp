#!/bin/bash
# Provision with Terraform, build and push the app image, roll it out and check /health.
# The CI pipeline (.github/workflows/archboard.yml) runs the same steps.
#   terraform/deploy.sh              # provision (terraform apply) + deploy
#   SKIP_APPLY=1 terraform/deploy.sh # code-only deploy
set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$TF_DIR")"
export AWS_PROFILE="${AWS_PROFILE:-jsolisdev}"

cd "$TF_DIR"
terraform init -input=false > /dev/null
if [ -z "${SKIP_APPLY:-}" ]; then
  terraform apply -input=false -auto-approve
fi

REPO=$(terraform output -raw ecr_repository_url)
REGION=$(terraform output -raw region)
INSTANCE=$(terraform output -raw instance_id)
URL=$(terraform output -raw url)
TAG=$(git -C "$ROOT" rev-parse --short=7 HEAD)

echo "==> Building $REPO:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 --build-arg APP_VERSION="$TAG" -t "$REPO:$TAG" -t "$REPO:latest" "$ROOT"
docker push "$REPO:$TAG"
docker push "$REPO:latest"

"$TF_DIR/rollout.sh" "$REGION" "$INSTANCE"
"$TF_DIR/healthcheck.sh" "$URL" "$TAG"
