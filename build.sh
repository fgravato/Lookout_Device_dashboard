#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.0.0}"
ARCHIVE_NAME="lookout-mra-dashboard-v${VERSION}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
ARCHIVE_PATH="${DIST_DIR}/${ARCHIVE_NAME}.tar.gz"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

mkdir -p "${DIST_DIR}"

STAGE_ROOT="$(mktemp -d)"
trap 'rm -rf "${STAGE_ROOT}"' EXIT
STAGE_DIR="${STAGE_ROOT}/${ARCHIVE_NAME}"
mkdir -p "${STAGE_DIR}"

echo "Building ${ARCHIVE_PATH} from current working tree..."
rsync -a \
    --exclude='.env' \
    --exclude='tenants.json' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='dashboard.log' \
    --exclude='*.db' \
    --exclude='CLAUDE.md' \
    --exclude='.git/' \
    --exclude='doc.json' \
    --exclude='tests/' \
    --exclude='setup.cfg' \
    --exclude='requirements-dev.txt' \
    --exclude='dist/' \
    --exclude='.claude/' \
    --exclude='.mypy_cache/' \
    --exclude='.pytest_cache/' \
    --exclude='.DS_Store' \
    "${REPO_ROOT}/" "${STAGE_DIR}/"

tar -czf "${ARCHIVE_PATH}" -C "${STAGE_ROOT}" "${ARCHIVE_NAME}"

echo "Running safety check for secrets/build artifacts in archive..."
if tar -tzf "${ARCHIVE_PATH}" | grep -E '\.env$|tenants\.json$|venv/|__pycache__|\.git/|tests/|setup\.cfg|\.claude/|\.mypy_cache/|\.pytest_cache/|\.DS_Store$'; then
    echo "ERROR: Archive contains files that should never ship (.env, tenants.json, venv/, __pycache__, .git/, tests/, setup.cfg, .claude/, .mypy_cache/, .pytest_cache/, or .DS_Store). Aborting build." >&2
    exit 1
fi

shasum -a 256 "${ARCHIVE_PATH}" > "${CHECKSUM_PATH}"

ARCHIVE_SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)

echo ""
echo "Build complete:"
echo "  Archive:  ${ARCHIVE_PATH} (${ARCHIVE_SIZE})"
echo "  Checksum: ${CHECKSUM_PATH}"
