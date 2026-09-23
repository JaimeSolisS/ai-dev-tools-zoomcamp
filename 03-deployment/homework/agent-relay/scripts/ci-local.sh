#!/usr/bin/env bash
# Run .github/workflows/ci.yml locally with act against the kind cluster.
#
# act starts job containers on the Docker daemon's host network and mounts the
# Docker socket into them, so a job can build images on the host daemon, run
# `kind load docker-image`, and reach the kind API server at the same
# 127.0.0.1:<port> address that the host kubeconfig uses.
set -euo pipefail

cluster="${KIND_CLUSTER_NAME:-agent-relay}"
kubeconfig=$(kind get kubeconfig --name "$cluster" | base64 | tr -d '\n')

exec act push -s KUBECONFIG_DATA="$kubeconfig" "$@"
