#!/usr/bin/env bash
# One-command installer for the Phishing Data Generator.
#
#   curl -fsSL https://raw.githubusercontent.com/VibeATSCoder/phishint-data-generator/main/install.sh | bash
#
# Local and advanced usage:
#
#   bash install.sh
#   bash install.sh --dir ~/phishint-data-generator
#   bash install.sh --download-only
#   bash install.sh --no-build
#   bash install.sh --no-prompt
#   bash install.sh --no-install
#
# The installer is safe to run again. It keeps an existing .env and data/
# directory, fast-forwards a clean Git checkout, and lets Docker Compose reuse
# images and containers that already exist.
set -euo pipefail

# Keep the script in a single compound command. When invoked through
# `curl ... | bash`, Bash parses the closing brace before executing anything,
# so a truncated download cannot run a partial installer.
{

OWNER="${GITHUB_OWNER:-VibeATSCoder}"
REPOSITORY="${GITHUB_REPOSITORY_NAME:-phishint-data-generator}"
BRANCH="${PHISHGEN_INSTALL_BRANCH:-main}"
REPO_URL="${PHISHGEN_REPO_URL:-https://github.com/${OWNER}/${REPOSITORY}.git}"

if [ -f "${PWD}/docker-compose.yml" ] \
   && [ -f "${PWD}/Dockerfile" ] \
   && [ -f "${PWD}/.env.example" ]; then
  INSTALL_DIR="${PWD}"
else
  INSTALL_DIR="${PHISHGEN_INSTALL_DIR:-${PWD}/${REPOSITORY}}"
fi

DOWNLOAD_ONLY=0
NO_BUILD=0
NO_PROMPT=0
NO_INSTALL=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Install and start the Phishing Data Generator with Docker Compose.

Usage:
  bash install.sh [options]
  curl -fsSL https://raw.githubusercontent.com/VibeATSCoder/phishint-data-generator/main/install.sh | bash

Options:
  --dir PATH          Install into PATH (default: ./phishint-data-generator)
  --branch NAME       Git branch or tag to install (default: main)
  --download-only     Clone/update and configure, but do not build or start
  --no-start          Alias for --download-only
  --no-build          Start with existing Docker images without rebuilding
  --no-prompt         Do not ask for optional API keys or dependency changes
  --no-install        Never offer to install missing system dependencies
  -y, --yes           Accept dependency and daemon-start prompts
  -h, --help          Show this help

Environment overrides:
  PHISHGEN_INSTALL_DIR, PHISHGEN_INSTALL_BRANCH, PHISHGEN_REPO_URL,
  GITHUB_OWNER, GITHUB_REPOSITORY_NAME, ANTHROPIC_API_KEY,
  CLEARBIT_API_KEY
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir)
      [ "$#" -ge 2 ] || { echo "--dir needs a path" >&2; exit 2; }
      INSTALL_DIR="$2"; shift 2 ;;
    --branch)
      [ "$#" -ge 2 ] || { echo "--branch needs a name" >&2; exit 2; }
      BRANCH="$2"; shift 2 ;;
    --download-only|--no-start) DOWNLOAD_ONLY=1; shift ;;
    --no-build) NO_BUILD=1; shift ;;
    --no-prompt) NO_PROMPT=1; shift ;;
    --no-install) NO_INSTALL=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

die() {
  echo >&2
  echo "install failed: $*" >&2
  exit 1
}

step() {
  echo
  echo "== $*"
}

warn() {
  echo "warning: $*" >&2
}

HAVE_TTY=0
if { exec 3<>/dev/tty; } 2>/dev/null; then
  HAVE_TTY=1
  exec 3>&-
fi

ask() { # prompt default -> answer on stdout
  local prompt="$1" default="${2:-}" reply=""
  if [ "${HAVE_TTY}" -eq 0 ] || [ "${NO_PROMPT}" -eq 1 ]; then
    printf '%s' "${default}"
    return 1
  fi
  printf '%s' "${prompt}" > /dev/tty
  if ! IFS= read -r reply < /dev/tty; then
    printf '%s' "${default}"
    return 1
  fi
  printf '%s' "${reply:-${default}}"
}

ask_secret() { # prompt -> secret on stdout
  local prompt="$1" reply=""
  if [ "${HAVE_TTY}" -eq 0 ] || [ "${NO_PROMPT}" -eq 1 ]; then
    return 1
  fi
  printf '%s' "${prompt}" > /dev/tty
  if ! IFS= read -rs reply < /dev/tty; then
    printf '\n' > /dev/tty
    return 1
  fi
  printf '\n' > /dev/tty
  printf '%s' "${reply}"
}

confirm() { # prompt default(y|n)
  local prompt="$1" default="${2:-n}" answer
  if [ "${ASSUME_YES}" -eq 1 ]; then
    return 0
  fi
  answer="$(ask "${prompt}" "${default}" || true)"
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

detect_package_manager() {
  local manager
  for manager in apt-get dnf yum zypper pacman apk; do
    if command -v "${manager}" >/dev/null 2>&1; then
      printf '%s' "${manager}"
      return 0
    fi
  done
  return 1
}

install_packages() { # package-manager packages...
  local manager="$1"
  shift
  case "${manager}" in
    apt-get)
      ${SUDO} env DEBIAN_FRONTEND=noninteractive apt-get update -qq
      ${SUDO} env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
    dnf) ${SUDO} dnf install -y -q "$@" ;;
    yum) ${SUDO} yum install -y -q "$@" ;;
    zypper) ${SUDO} zypper --non-interactive install "$@" ;;
    pacman) ${SUDO} pacman -Sy --noconfirm "$@" ;;
    apk) ${SUDO} apk add --no-cache "$@" ;;
    *) return 1 ;;
  esac
}

ensure_clone_tools() {
  local missing="" manager=""
  command -v git >/dev/null 2>&1 || missing="${missing} git"
  command -v curl >/dev/null 2>&1 || missing="${missing} curl"
  [ -z "${missing}" ] && return 0

  [ "${NO_INSTALL}" -eq 0 ] || die "missing:${missing}; install them and run again"
  [ "${HAVE_TTY}" -eq 1 ] || die "missing:${missing}; install them and run again"
  [ -n "${SUDO}" ] || [ "$(id -u)" -eq 0 ] \
    || die "missing:${missing}; root or sudo is required to install them"
  manager="$(detect_package_manager || true)"
  [ -n "${manager}" ] || die "missing:${missing}; no supported package manager was found"
  confirm "Install${missing} with ${manager}? [Y/n]: " y \
    || die "missing:${missing}"
  # git and curl use these names on every supported manager.
  # shellcheck disable=SC2086
  install_packages "${manager}" ${missing} \
    || die "could not install:${missing}"
}

clone_or_update() {
  local parent
  parent="$(dirname "${INSTALL_DIR}")"
  mkdir -p "${parent}"

  if [ ! -e "${INSTALL_DIR}" ]; then
    step "downloading source"
    if command -v gh >/dev/null 2>&1 \
       && gh auth status >/dev/null 2>&1 \
       && [ "${REPO_URL}" = "https://github.com/${OWNER}/${REPOSITORY}.git" ]; then
      gh repo clone "${OWNER}/${REPOSITORY}" "${INSTALL_DIR}" -- \
        --depth 1 --branch "${BRANCH}" \
        || die "could not clone ${OWNER}/${REPOSITORY}"
    else
      git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}" \
        || die "could not clone ${REPO_URL}. If it is private, authenticate with gh first or set PHISHGEN_REPO_URL."
    fi
    return
  fi

  [ -d "${INSTALL_DIR}" ] || die "${INSTALL_DIR} exists and is not a directory"
  [ -f "${INSTALL_DIR}/docker-compose.yml" ] \
    || die "${INSTALL_DIR} exists but is not a Phishing Data Generator checkout"

  if [ -d "${INSTALL_DIR}/.git" ]; then
    step "checking existing source"
    if [ -n "$(git -C "${INSTALL_DIR}" status --porcelain 2>/dev/null)" ]; then
      warn "${INSTALL_DIR} has local changes; keeping them and skipping the Git update"
    else
      git -C "${INSTALL_DIR}" fetch --depth 1 origin "${BRANCH}" \
        || die "could not fetch ${BRANCH}"
      git -C "${INSTALL_DIR}" merge --ff-only FETCH_HEAD \
        || die "the checkout cannot be fast-forwarded; update it manually"
      echo "  source is up to date"
    fi
  else
    warn "${INSTALL_DIR} is not a Git checkout; using its existing files"
  fi
}

env_value() { # key
  local key="$1"
  sed -n "s/^${key}=//p" .env 2>/dev/null | tail -n 1
}

set_env_value() { # key value
  local key="$1" value="$2" tmp found=0 line
  tmp=".env.tmp.$$"
  : > "${tmp}"
  if [ -f .env ]; then
    while IFS= read -r line || [ -n "${line}" ]; do
      case "${line}" in
        "${key}="*)
          if [ "${found}" -eq 0 ]; then
            printf '%s=%s\n' "${key}" "${value}" >> "${tmp}"
            found=1
          fi ;;
        *) printf '%s\n' "${line}" >> "${tmp}" ;;
      esac
    done < .env
  fi
  if [ "${found}" -eq 0 ]; then
    printf '%s=%s\n' "${key}" "${value}" >> "${tmp}"
  fi
  mv "${tmp}" .env
}

configure_environment() {
  local created=0 existing="" secret=""
  step "configuration"
  if [ ! -f .env ]; then
    umask 077
    cp .env.example .env
    # The example contains documentation placeholders. A blank key correctly
    # disables T23 until the operator configures it.
    set_env_value ANTHROPIC_API_KEY ""
    set_env_value CLEARBIT_API_KEY ""
    created=1
    echo "  wrote ${INSTALL_DIR}/.env"
  else
    echo "  keeping ${INSTALL_DIR}/.env"
  fi
  chmod 600 .env 2>/dev/null || true

  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    set_env_value ANTHROPIC_API_KEY "${ANTHROPIC_API_KEY}"
    echo "  saved ANTHROPIC_API_KEY from the environment"
  elif [ "${NO_PROMPT}" -eq 0 ] && [ "${HAVE_TTY}" -eq 1 ]; then
    existing="$(env_value ANTHROPIC_API_KEY)"
    if [ -z "${existing}" ] && confirm "Configure the optional Anthropic key for T23 now? [y/N]: " n; then
      secret="$(ask_secret 'Anthropic API key (hidden): ' || true)"
      [ -z "${secret}" ] || set_env_value ANTHROPIC_API_KEY "${secret}"
    fi
  fi

  if [ -n "${CLEARBIT_API_KEY:-}" ]; then
    set_env_value CLEARBIT_API_KEY "${CLEARBIT_API_KEY}"
    echo "  saved CLEARBIT_API_KEY from the environment"
  fi

  mkdir -p data
  if [ "${created}" -eq 1 ]; then
    echo "  optional keys can be added later in ${INSTALL_DIR}/.env"
  fi
}

install_docker_engine() {
  local script
  [ "$(uname -s)" = "Linux" ] \
    || die "Docker is missing. Install Docker Desktop, start it, and rerun this installer."
  [ "${NO_INSTALL}" -eq 0 ] \
    || die "Docker is missing; install Docker Engine with the Compose v2 plugin and rerun"
  [ "${HAVE_TTY}" -eq 1 ] \
    || die "Docker is missing; install Docker Engine with the Compose v2 plugin and rerun"
  [ -n "${SUDO}" ] || [ "$(id -u)" -eq 0 ] \
    || die "Docker is missing and root or sudo is required to install it"
  confirm "Install Docker Engine and Compose v2 using get.docker.com? [Y/n]: " y \
    || die "Docker is required"
  script="$(mktemp)"
  curl -fsSL --connect-timeout 15 --max-time 120 https://get.docker.com -o "${script}" \
    || { rm -f "${script}"; die "could not download the Docker installer"; }
  ${SUDO} sh "${script}" || { rm -f "${script}"; die "Docker installation failed"; }
  rm -f "${script}"
}

DOCKER=(docker)

prepare_docker() {
  step "Docker"
  command -v docker >/dev/null 2>&1 || install_docker_engine
  command -v docker >/dev/null 2>&1 || die "Docker is still unavailable after installation"

  if ! docker info >/dev/null 2>&1; then
    if command -v systemctl >/dev/null 2>&1 \
       && [ "${NO_INSTALL}" -eq 0 ] \
       && confirm "Docker is installed but unavailable. Start its daemon now? [Y/n]: " y; then
      ${SUDO} systemctl enable --now docker >/dev/null 2>&1 || true
    fi
  fi

  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif [ -n "${SUDO}" ] && sudo docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
    warn "Docker requires sudo for this user. Add $(id -un) to the docker group for passwordless use."
  else
    die "cannot reach the Docker daemon. Start Docker, or add $(id -un) to the docker group, then rerun."
  fi

  "${DOCKER[@]}" compose version >/dev/null 2>&1 \
    || die "Docker Compose v2 is missing. Install the docker-compose-plugin and rerun."
  echo "  $("${DOCKER[@]}" --version)"
  echo "  $("${DOCKER[@]}" compose version)"
}

check_disk_space() {
  local available_kb
  available_kb="$(df -Pk . 2>/dev/null | awk 'NR==2 {print $4}')"
  case "${available_kb}" in
    ''|*[!0-9]*) return ;;
  esac
  if [ "${available_kb}" -lt 8388608 ]; then
    warn "less than 8 GB is free on the install volume. Docker builds and screenshot jobs can exhaust it."
  fi
}

wait_for_health() {
  local attempts=0
  while [ "${attempts}" -lt 120 ]; do
    if curl -fsS --max-time 2 http://127.0.0.1:8009/health >/dev/null 2>&1 \
       && curl -fsS --max-time 2 http://127.0.0.1:3050/health >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  return 1
}

ensure_clone_tools
INSTALL_DIR="$(mkdir -p "$(dirname "${INSTALL_DIR}")" && cd "$(dirname "${INSTALL_DIR}")" && pwd)/$(basename "${INSTALL_DIR}")"
clone_or_update
cd "${INSTALL_DIR}"
configure_environment

if [ "${DOWNLOAD_ONLY}" -eq 1 ]; then
  echo
  echo "Source and configuration are ready in ${INSTALL_DIR}."
  echo "Start later with:"
  echo "  cd '${INSTALL_DIR}' && docker compose up --build -d"
  exit 0
fi

prepare_docker
check_disk_space

step "validating Compose configuration"
"${DOCKER[@]}" compose config --quiet \
  || die "docker-compose.yml or .env is invalid"

step "building and starting"
if [ "${NO_BUILD}" -eq 1 ]; then
  "${DOCKER[@]}" compose up -d
else
  "${DOCKER[@]}" compose up --build -d
fi

step "waiting for services"
if ! wait_for_health; then
  "${DOCKER[@]}" compose ps || true
  die "the services did not become healthy within 120 seconds. Run: cd '${INSTALL_DIR}' && docker compose logs --tail=100"
fi

echo "  backend and UI are healthy"
echo
echo "Phishing Data Generator is ready."
echo "  UI:       http://127.0.0.1:3050/"
echo "  API:      http://127.0.0.1:8009/"
echo "  API docs: http://127.0.0.1:8009/docs"
echo "  Data:     ${INSTALL_DIR}/data"
echo
echo "Manage it from ${INSTALL_DIR}:"
echo "  docker compose ps"
echo "  docker compose logs -f"
echo "  docker compose down"

} # end parse-before-execute block
