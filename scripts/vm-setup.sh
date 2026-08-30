#!/usr/bin/env bash
set -euo pipefail

# Clone (or reuse) the API repo, start compose.vm.yaml, install the nginx
# server_name, and request a cert. Does not start Caddy.
#
#   ./scripts/vm-setup.sh pranav-linkedin-api-tross.duckdns.org
#   DUCKDNS_HOSTNAME=example.duckdns.org ./scripts/vm-setup.sh

REPO_URL="${REPO_URL:-https://github.com/Pranav5255/linkedin-profile-api.git}"
SITE_NAME="${SITE_NAME:-linkedin-duckdns}"
OPS_DIR="${OPS_DIR:-${HOME}/.local/share/linkedin-profile-api}"
COMPOSE_FILE="compose.vm.yaml"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-90}"
HEALTH_POLL_SECONDS="${HEALTH_POLL_SECONDS:-2}"

die() {
  echo "error: $*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

wait_for_health() {
  local url="$1"
  local deadline started now
  started="$(date +%s)"
  deadline=$((started + HEALTH_TIMEOUT_SECONDS))
  echo "waiting up to ${HEALTH_TIMEOUT_SECONDS}s for ${url}"
  while true; do
    if curl -fsS --max-time 5 "${url}" >/dev/null 2>&1; then
      echo "API is healthy"
      return 0
    fi
    now="$(date +%s)"
    if (( now >= deadline )); then
      die "API did not become healthy on ${url} within ${HEALTH_TIMEOUT_SECONDS}s"
    fi
    sleep "${HEALTH_POLL_SECONDS}"
  done
}

detect_repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "${here}/${COMPOSE_FILE}" && -f "${here}/deploy/nginx-linkedin-duckdns.conf" ]]; then
    printf '%s\n' "${here}"
    return 0
  fi
  return 1
}

install_packages_if_needed() {
  local missing=()
  command -v nginx >/dev/null 2>&1 || missing+=(nginx)
  command -v certbot >/dev/null 2>&1 || missing+=(certbot)
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi
  command -v apt-get >/dev/null 2>&1 || die "install ${missing[*]} then re-run"
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx
}

ensure_env_file() {
  local env_path="$1/.env"
  if [[ ! -f "${env_path}" ]]; then
    cp "$1/.env.example" "${env_path}"
    chmod 600 "${env_path}"
    die "created ${env_path} from .env.example. Fill API_KEY and LINKEDIN_COOKIE_JAR, then re-run."
  fi
  chmod 600 "${env_path}"
  if ! grep -qE '^API_KEY=.+' "${env_path}"; then
    die "${env_path} is missing API_KEY"
  fi
  if ! grep -qE '^LINKEDIN_COOKIE_JAR=.+' "${env_path}" && ! grep -qE '^LINKEDIN_LI_AT=.+' "${env_path}"; then
    die "${env_path} is missing LINKEDIN_COOKIE_JAR (or LINKEDIN_LI_AT + LINKEDIN_JSESSIONID)"
  fi
  if grep -qE '^DUCKDNS_HOSTNAME=$' "${env_path}" || ! grep -qE '^DUCKDNS_HOSTNAME=' "${env_path}"; then
    if grep -qE '^DUCKDNS_HOSTNAME=' "${env_path}"; then
      sed -i "s|^DUCKDNS_HOSTNAME=.*|DUCKDNS_HOSTNAME=${DUCKDNS_HOSTNAME}|" "${env_path}"
    else
      printf '\nDUCKDNS_HOSTNAME=%s\n' "${DUCKDNS_HOSTNAME}" >>"${env_path}"
    fi
  fi
}

install_nginx_site() {
  local repo="$1"
  local src="${repo}/deploy/nginx-linkedin-duckdns.conf"
  local dest
  [[ -f "${src}" ]] || die "missing ${src}"

  if [[ -d /etc/nginx/sites-available ]]; then
    dest="/etc/nginx/sites-available/${SITE_NAME}"
    sudo cp "${src}" "${dest}"
    sudo sed -i "s/YOUR_DUCKDNS_HOST/${DUCKDNS_HOSTNAME}/g" "${dest}"
    sudo ln -sfn "${dest}" "/etc/nginx/sites-enabled/${SITE_NAME}"
  else
    dest="/etc/nginx/conf.d/${SITE_NAME}.conf"
    sudo cp "${src}" "${dest}"
    sudo sed -i "s/YOUR_DUCKDNS_HOST/${DUCKDNS_HOSTNAME}/g" "${dest}"
  fi
  sudo nginx -t
  sudo systemctl enable --now nginx
  sudo systemctl reload nginx
}

request_cert() {
  if [[ "${SKIP_CERTBOT:-}" == "1" ]]; then
    echo "skipping certbot (SKIP_CERTBOT=1)"
    return 0
  fi
  if [[ -d "/etc/letsencrypt/live/${DUCKDNS_HOSTNAME}" ]]; then
    echo "cert already exists for ${DUCKDNS_HOSTNAME}"
    return 0
  fi
  local args=(--nginx -d "${DUCKDNS_HOSTNAME}")
  if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
    args+=(--non-interactive --agree-tos -m "${CERTBOT_EMAIL}")
  fi
  sudo certbot "${args[@]}"
}

main() {
  DUCKDNS_HOSTNAME="${1:-${DUCKDNS_HOSTNAME:-}}"
  [[ -n "${DUCKDNS_HOSTNAME}" ]] || die "usage: $0 <duckdns-hostname>"
  [[ "${DUCKDNS_HOSTNAME}" != *://* ]] || die "hostname only, no https://"
  [[ "${DUCKDNS_HOSTNAME}" != */ ]] || die "hostname only, no trailing slash"

  need git
  need docker
  docker compose version >/dev/null 2>&1 || die "docker compose plugin is required"
  install_packages_if_needed
  need nginx
  need certbot

  local repo
  if repo="$(detect_repo_root)"; then
    echo "using existing checkout ${repo}"
  else
    repo="${INSTALL_DIR:-${HOME}/linkedin-profile-api}"
    if [[ -d "${repo}/.git" ]]; then
      echo "using ${repo}"
    else
      git clone "${REPO_URL}" "${repo}"
    fi
  fi
  [[ -f "${repo}/${COMPOSE_FILE}" ]] || die "${repo} is not this project"

  mkdir -p "${OPS_DIR}"
  cp "${repo}/scripts/vm-setup.sh" "${repo}/scripts/vm-destroy.sh" "${OPS_DIR}/"
  chmod 755 "${OPS_DIR}/vm-setup.sh" "${OPS_DIR}/vm-destroy.sh"
  printf '%s\n' "${repo}" >"${OPS_DIR}/install-dir"
  printf '%s\n' "${DUCKDNS_HOSTNAME}" >"${OPS_DIR}/hostname"

  ensure_env_file "${repo}"

  (cd "${repo}" && docker compose -f "${COMPOSE_FILE}" up -d --build)
  wait_for_health "http://127.0.0.1:8080/healthz"

  install_nginx_site "${repo}"
  request_cert

  echo
  echo "setup complete"
  echo "  repo    ${repo}"
  echo "  ops     ${OPS_DIR}"
  echo "  health  https://${DUCKDNS_HOSTNAME}/healthz"
  echo "  docs    https://${DUCKDNS_HOSTNAME}/docs"
  echo "destroy: ${OPS_DIR}/vm-destroy.sh"
}

main "$@"
