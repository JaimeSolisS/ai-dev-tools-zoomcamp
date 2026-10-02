#!/bin/bash
# Make the EC2 instance pull the latest image from ECR and restart the app (via SSM).
#   rollout.sh <region> <instance-id>
set -euo pipefail
REGION=$1
INSTANCE=$2

echo "==> Waiting for $INSTANCE to register with SSM"
for _ in $(seq 1 60); do
  status=$(aws ssm describe-instance-information --region "$REGION" \
    --filters "Key=InstanceIds,Values=$INSTANCE" \
    --query 'InstanceInformationList[0].PingStatus' --output text)
  [ "$status" = "Online" ] && break
  sleep 5
done
[ "$status" = "Online" ] || { echo "$INSTANCE never came online in SSM" >&2; exit 1; }

echo "==> Restarting the app on $INSTANCE"
# cloud-init first: on a new instance, deploy.sh is written by the boot script.
CMD_ID=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cloud-init status --wait > /dev/null","/opt/archboard/deploy.sh"]' \
  --query Command.CommandId --output text)

ok=0
aws ssm wait command-executed --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" || ok=$?
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
  --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
exit $ok
