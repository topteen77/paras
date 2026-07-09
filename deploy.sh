#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Local Docker setup for Canam Assistant
#
# Usage:
#   ./deploy.sh          # build and start all services
#   ./deploy.sh stop     # stop containers
#   ./deploy.sh logs     # tail logs
#   ./deploy.sh restart  # rebuild and restart
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${ROOT_DIR}/canam-assistant"
ENV_FILE="${APP_DIR}/.env"
ENV_EXAMPLE="${APP_DIR}/.env.example"
SA_KEY="${APP_DIR}/service_account_key.json"
SA_KEY_EXAMPLE="${APP_DIR}/service_account_key.json.example"
UPLOADS_DIR="${APP_DIR}/uploads"
RECORDINGS_DIR="${ROOT_DIR}/call-recordings"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

require_command() {
  if ! command -v "$1" &>/dev/null; then
    error "$1 is not installed. Please install it and retry."
    exit 1
  fi
}

setup_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f "${ENV_EXAMPLE}" ]]; then
      cp "${ENV_EXAMPLE}" "${ENV_FILE}"
      warn "Created ${ENV_FILE} from .env.example — edit it with your credentials."
    else
      error "Missing ${ENV_FILE} and ${ENV_EXAMPLE}"
      exit 1
    fi
  fi
}

setup_gcp_key() {
  if [[ ! -f "${SA_KEY}" ]]; then
    if [[ -f "${SA_KEY_EXAMPLE}" ]]; then
      cp "${SA_KEY_EXAMPLE}" "${SA_KEY}"
      warn "Created placeholder ${SA_KEY}"
      warn "Replace it with a real GCP service account JSON before making calls."
      warn "Download from: GCP Console → IAM → Service Accounts → Keys"
    else
      error "Missing GCP service account key at ${SA_KEY}"
      exit 1
    fi
  fi
}

setup_uploads() {
  mkdir -p "${UPLOADS_DIR}"
}

setup_call_recordings() {
  mkdir -p "${RECORDINGS_DIR}"
}

check_env_values() {
  local missing=()
  while IFS= read -r line; do
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    if [[ "${line}" =~ ^([A-Z_]+)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      if [[ "${val}" == "CHANGE_ME" || "${val}" == "your_"* ]]; then
        missing+=("${key}")
      fi
    fi
  done < "${ENV_FILE}"

  if [[ ${#missing[@]} -gt 0 ]]; then
    warn "These .env values still use placeholders (calls will fail until set):"
    for key in "${missing[@]}"; do
      echo "         - ${key}"
    done
  fi
}

get_ngrok_url() {
  local retries=15
  local url=""
  for ((i=1; i<=retries; i++)); do
    url=$(curl -sf http://localhost:4040/api/tunnels 2>/dev/null \
      | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for t in data.get('tunnels', []):
        if t.get('proto') == 'https':
            print(t['public_url'])
            break
except Exception:
    pass
" 2>/dev/null || true)
    if [[ -n "${url}" ]]; then
      echo "${url}"
      return 0
    fi
    sleep 2
  done
  return 1
}

update_ngrok_url_in_env() {
  local url
  url=$(get_ngrok_url) || return 1

  if grep -q "^NGROK_URL=" "${ENV_FILE}"; then
    sed -i "s|^NGROK_URL=.*|NGROK_URL=${url}|" "${ENV_FILE}"
  else
    echo "NGROK_URL=${url}" >> "${ENV_FILE}"
  fi

  if grep -q "^WEB_SERVER_URL=" "${ENV_FILE}"; then
    sed -i "s|^WEB_SERVER_URL=.*|WEB_SERVER_URL=${url}|" "${ENV_FILE}"
  else
    echo "WEB_SERVER_URL=${url}" >> "${ENV_FILE}"
  fi

  info "Updated NGROK_URL and WEB_SERVER_URL in .env → ${url}"
}

wait_for_health() {
  local port
  port=$(get_app_port)
  local retries=30
  for ((i=1; i<=retries; i++)); do
    if curl -sf "http://localhost:${port}/health" &>/dev/null; then
      return 0
    fi
    sleep 2
  done
  error "Service did not become healthy on port ${port}"
  return 1
}

get_app_port() {
  local port="8080"
  if [[ -f "${ENV_FILE}" ]]; then
    port=$(grep -E '^PORT=' "${ENV_FILE}" | cut -d= -f2 | tr -d '[:space:]' || true)
    port="${port:-8080}"
  fi
  echo "${port}"
}

NGROK_DASHBOARD_PORT="4040"

is_port_in_use() {
  local port="$1"
  if command -v ss &>/dev/null; then
    ss -tlnH "sport = :${port}" 2>/dev/null | grep -q .
    return $?
  fi
  if command -v lsof &>/dev/null; then
    lsof -iTCP:"${port}" -sTCP:LISTEN -t &>/dev/null
    return $?
  fi
  return 1
}

is_project_container_name() {
  local name="$1"
  [[ "${name}" == "canam-assistant" || "${name}" == "canam-ngrok" || "${name}" == canam-assistant-* ]]
}

containers_on_port() {
  local port="$1"
  docker ps --format '{{.ID}}\t{{.Names}}\t{{.Ports}}' 2>/dev/null \
    | awk -v port=":${port}->" '$0 ~ port {print $1 "\t" $2}'
}

stop_container_by_id() {
  local container_id="$1"
  [[ -z "${container_id}" ]] && return 0
  docker stop "${container_id}" &>/dev/null || true
  docker rm -f "${container_id}" &>/dev/null || true
}

free_port_if_project_container() {
  local port="$1"
  local label="$2"
  local rows found=0
  local container_id container_name

  if ! is_port_in_use "${port}"; then
    info "Port ${port} (${label}) is free."
    return 0
  fi

  rows=$(containers_on_port "${port}" || true)
  if [[ -z "${rows}" ]]; then
    warn "Port ${port} (${label}) is in use by a non-Docker process. Stop it manually, then retry."
    return 1
  fi

  while IFS=$'\t' read -r container_id container_name; do
    [[ -z "${container_id}" ]] && continue
    found=1
    if is_project_container_name "${container_name}"; then
      info "Stopping ${container_name} to free port ${port} (${label})..."
      stop_container_by_id "${container_id}"
    else
      warn "Port ${port} (${label}) is used by '${container_name}'. Stop it manually, then retry."
      return 1
    fi
  done <<< "${rows}"

  if [[ "${found}" -eq 0 ]]; then
    warn "Port ${port} (${label}) is in use but no Docker mapping was found. Stop the process manually."
    return 1
  fi

  local wait_seconds=15
  for ((i=1; i<=wait_seconds; i++)); do
    if ! is_port_in_use "${port}"; then
      info "Port ${port} (${label}) released."
      return 0
    fi
    sleep 1
  done

  error "Port ${port} (${label}) is still in use after stopping project containers."
  return 1
}

stop_project_containers() {
  cd "${APP_DIR}"
  info "Stopping project containers..."
  docker compose down --remove-orphans 2>/dev/null || true

  for name in canam-assistant canam-ngrok; do
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "${name}"; then
      info "Removing leftover container: ${name}"
      docker rm -f "${name}" &>/dev/null || true
    fi
  done
}

ensure_ports_available() {
  local app_port
  app_port=$(get_app_port)

  stop_project_containers

  free_port_if_project_container "${app_port}" "API" || return 1
  free_port_if_project_container "${NGROK_DASHBOARD_PORT}" "ngrok dashboard" || return 1
}

cmd_start() {
  require_command docker
  require_command curl
  require_command python3

  if ! docker compose version &>/dev/null; then
    error "docker compose is not available. Install Docker Compose v2."
    exit 1
  fi

  setup_env
  setup_gcp_key
  setup_uploads
  setup_call_recordings
  check_env_values

  ensure_ports_available

  info "Building and starting containers..."
  cd "${APP_DIR}"
  docker compose up -d --build

  info "Waiting for canam-assistant to be healthy..."
  wait_for_health

  local port
  port=$(get_app_port)

  info "Fetching ngrok public URL..."
  if update_ngrok_url_in_env; then
    docker compose restart canam-assistant
    sleep 3
    wait_for_health
  else
    warn "Could not detect ngrok tunnel. Check NGROK_AUTHTOKEN in .env"
    warn "Ngrok dashboard: http://localhost:4040"
  fi

  echo ""
  echo "============================================"
  info "Canam Assistant is running locally!"
  echo "============================================"
  echo ""
  echo "  API (local):     http://localhost:${port}"
  echo "  API docs:        http://localhost:${port}/docs"
  echo "  Health check:    http://localhost:${port}/health"
  echo "  Ngrok dashboard: http://localhost:4040"
  if grep -qE '^NGROK_URL=https://' "${ENV_FILE}"; then
    echo "  Public URL:      $(grep '^NGROK_URL=' "${ENV_FILE}" | cut -d= -f2-)"
  fi
  echo ""
  echo "  Test schedule a call:"
  echo "    curl -X POST http://localhost:${port}/make-call \\"
  echo "      -H 'Content-Type: application/json' \\"
  echo "      -d '{\"to\": \"+91XXXXXXXXXX\"}'"
  echo ""
  echo "  Trigger batch processor (required after /make-call):"
  echo "    curl -X POST http://localhost:${port}/create-scheduled-task"
  echo ""
  echo "  View logs:"
  echo "    ./deploy.sh logs"
  echo ""
  warn "Before live calls, ensure .env has real credentials (not CHANGE_ME)."
  warn "assistantFunctions-main runs on GCP Cloud Functions — deploy separately."
  echo ""
}

cmd_stop() {
  stop_project_containers
  info "Containers stopped."
}

cmd_logs() {
  cd "${APP_DIR}"
  docker compose logs -f
}

cmd_restart() {
  cmd_start
}

ACTION="${1:-start}"

case "${ACTION}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  logs)    cmd_logs ;;
  restart) cmd_restart ;;
  *)
    echo "Usage: $0 {start|stop|logs|restart}"
    exit 1
    ;;
esac
