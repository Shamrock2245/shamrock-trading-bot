#!/usr/bin/env bash
# Free disk on the paper server before and after an image build.
#
# prebuild: delete the BuildKit cache (a failed deploy's cache is what fills
# the disk; an age filter does not remove it) and dangling images, then exit
# non-zero if less than DEPLOY_MIN_FREE_GB is free. Running containers are
# left up. Volumes are never pruned — optuna_studies.db, trade journals, and
# the db-data volume stay on disk.
#
# postdeploy: drop unused images and the cache created by the build that just
# succeeded. Best-effort: a prune error must not fail a deploy that is already
# healthy.
set -euo pipefail

MIN_FREE_GB="${DEPLOY_MIN_FREE_GB:-12}"

avail_kb() {
  df -Pk / | tail -1 | awk '{print $4}'
}

case "${1:-}" in
  prebuild)
    echo "Disk before pre-build prune:"
    df -h /
    # -a all cache, -f no prompt. No --filter until=, no --volumes.
    docker builder prune -af
    docker image prune -f
    echo "Disk after pre-build prune:"
    df -h /
    docker system df || true

    free_kb="$(avail_kb)"
    if ! [[ "$free_kb" =~ ^[0-9]+$ ]]; then
      echo "ERROR: could not read free space from df -Pk / (got '${free_kb}')."
      df -Pk / || true
      exit 1
    fi
    need_kb=$((MIN_FREE_GB * 1024 * 1024))
    free_gb=$((free_kb / 1024 / 1024))
    if [ "$free_kb" -lt "$need_kb" ]; then
      echo "ERROR: Need at least ${MIN_FREE_GB}GB free on / before image build; have ${free_gb}GB."
      echo "Refusing to build. Running containers were not stopped and no volumes were pruned."
      exit 1
    fi
    echo "Pre-build disk check OK: ${free_gb}GB free (minimum ${MIN_FREE_GB}GB)."
    ;;
  postdeploy)
    echo "Disk before post-deploy prune:"
    df -h /
    docker image prune -af || echo "WARN: image prune failed"
    docker builder prune -af || echo "WARN: builder prune failed"
    echo "Disk after post-deploy prune:"
    df -h /
    ;;
  *)
    echo "usage: deploy_disk.sh prebuild|postdeploy" >&2
    exit 2
    ;;
esac
