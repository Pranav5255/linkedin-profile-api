#!/usr/bin/env bash
set -euo pipefail

# Tear down the VM API stack: compose project + volume, nginx site, cert,
# ops copies of these scripts, and the git checkout.
#
#   ./scripts/vm-destroy.sh
#   ~/.local/share/linkedin-profile-api/vm-destroy.sh

SITE_NAME="${SITE_NAME:-linkedin-duckdns}"
OPS_DIR="${OPS_DIR:-${HOME}/.local/share/linkedin-profile-api}"
COMPOSE_FILE="compose.vm.yaml"

die() {
  echo "error: $*" >&2
  exit 1
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

resolve_install_dir() {
  if [[ -n "${INSTALL_DIR:-}" ]]; then
    printf '%s\n' "${INSTALL_DIR}"
    return 0
  fi
  if [[ -f "${OPS_DIR}/install-dir" ]]; then
    cat "${OPS_DIR}/install-dir"
    return 0
  fi
  if detect_repo_root >/dev/null; then
    detect_repo_root
    return 0
  fi
  die "cannot find the checkout. Set INSTALL_DIR=..."
}

assert_safe_dir() {
  local dir="$1"
  [[ -n "${dir}" ]] || die "empty install dir"
  [[ "${dir}" != "/" ]] || die "refusing to delete /"
  [[ "${dir}" != "${HOME}" ]] || die "refusing to delete \$HOME"
  [[ -f "${dir}/${COMPOSE_FILE}" ]] || die "refusing to delete ${dir} (no ${COMPOSE_FILE})"
}

stop_compose() {
  local dir="$1"
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not installed; skipping compose down"
    return 0
  fi
  if [[ ! -f "${dir}/${COMPOSE_FILE}" ]]; then
    return 0
  fi
  (cd "${dir}" && docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans) || true
  docker image rm linkedin-profile-api:local >/dev/null 2>&1 || true
}

remove_nginx_site() {
  command -v nginx >/dev/null 2>&1 || return 0
  sudo rm -f "/etc/nginx/sites-enabled/${SITE_NAME}"
  sudo rm -f "/etc/nginx/sites-available/${SITE_NAME}"
  sudo rm -f "/etc/nginx/conf.d/${SITE_NAME}.conf"
  if sudo nginx -t >/dev/null 2>&1; then
    sudo systemctl reload nginx
  else
    echo "nginx -t failed after site removal; not reloading" >&2
  fi
}

remove_cert() {
  local host="${1:-}"
  if [[ -z "${host}" && -f "${OPS_DIR}/hostname" ]]; then
    host="$(cat "${OPS_DIR}/hostname")"
  fi
  [[ -n "${host}" ]] || return 0
  command -v certbot >/dev/null 2>&1 || return 0
  if [[ -d "/etc/letsencrypt/live/${host}" ]]; then
    sudo certbot delete --cert-name "${host}" --non-interactive || true
  fi
}

remove_tree() {
  local dir="$1"
  rm -rf "${OPS_DIR}"
  if [[ -d "${dir}" ]]; then
    rm -rf "${dir}"
  fi
}

main() {
  local repo
  repo="$(resolve_install_dir)"
  assert_safe_dir "${repo}"

  local host="${DUCKDNS_HOSTNAME:-}"
  if [[ -z "${host}" && -f "${OPS_DIR}/hostname" ]]; then
    host="$(cat "${OPS_DIR}/hostname")"
  fi

  echo "destroying ${repo}"
  stop_compose "${repo}"
  remove_nginx_site
  remove_cert "${host}"

  local running_from_repo=0
  case "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" in
    "${repo}"/*) running_from_repo=1 ;;
  esac

  if [[ "${running_from_repo}" -eq 1 ]]; then
    local tmp
    tmp="$(mktemp)"
    cp "${BASH_SOURCE[0]}" "${tmp}"
    chmod 700 "${tmp}"
    exec bash "${tmp}" --finish "${repo}"
  fi

  remove_tree "${repo}"
  echo "destroy complete"
}

if [[ "${1:-}" == "--finish" ]]; then
  remove_tree "${2:?}"
  rm -f "$0"
  echo "destroy complete"
  exit 0
fi

main "$@"
