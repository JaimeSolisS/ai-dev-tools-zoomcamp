#!/bin/bash
# Build the app image, push it to ECR and restart the app on the EC2 instance.
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
TAG=$(git -C "$ROOT" rev-parse --short HEAD)

echo "==> Building $REPO:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 -t "$REPO:$TAG" -t "$REPO:latest" "$ROOT"
docker push "$REPO:$TAG"
docker push "$REPO:latest"

echo "==> Waiting for $INSTANCE to register with SSM"
until [ "$(aws ssm describe-instance-information --region "$REGION" \
    --filters "Key=InstanceIds,Values=$INSTANCE" \
    --query 'InstanceInformationList[0].PingStatus' --output text)" = "Online" ]; do
  sleep 5
done

echo "==> Restarting the app on $INSTANCE"
CMD_ID=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cloud-init status --wait > /dev/null","/opt/archboard/deploy.sh"]' \
  --query Command.CommandId --output text)
aws ssm wait command-executed --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
  --query '[Status,StandardOutputContent,StandardErrorContent]' --output text

echo "==> Waiting for $URL"
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "$URL/"; then echo "Up: $URL"; exit 0; fi
  sleep 5
done
echo "App did not respond at $URL" >&2
exit 1
