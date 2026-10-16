#!/bin/bash
# Point this directory at one environment's state: dev and prod share the config and the
# bucket, but each has its own state key (envs/<env>.tfbackend).
#   init.sh <env>
set -euo pipefail
TF_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV=${1:?usage: init.sh <env>}
[ -f "$TF_DIR/envs/$ENV.tfbackend" ] || { echo "Unknown environment '$ENV' (see terraform/envs/)" >&2; exit 1; }
terraform -chdir="$TF_DIR" init -input=false -reconfigure -backend-config="envs/$ENV.tfbackend"
