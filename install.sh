#!/usr/bin/env bash
# One-command installer for the Phishing Data Generator.
#
#   curl -fsSL https://raw.githubusercontent.com/VibeATSCoder/phishint-data-generator/main/install.sh | bash
#
# Local and advanced usage:
#
#   bash install.sh
#   bash install.sh --dir ~/phishint-data-generator
#   bash install.sh --image ~/Downloads/phishint-data-generator-images-1.0.0.tar.gz
#   bash install.sh --manual
#   bash install.sh --auto-download
#   bash install.sh --build
#   bash install.sh --download-only
#   bash install.sh --no-prompt
#   bash install.sh --no-install
#
# The normal path loads prebuilt Docker images, so the target server does not
# download Python requirements, Chromium, or base-image layers. The installer
# is safe to run again. It keeps an existing .env and data/ directory,
# fast-forwards a clean Git checkout, and reuses loaded images and containers.
set -euo pipefail

# Keep the script in a single compound command. When invoked through
# `curl ... | bash`, Bash parses the closing brace before executing anything,
# so a truncated download cannot run a partial installer.
{

OWNER="${GITHUB_OWNER:-VibeATSCoder}"
REPOSITORY="${GITHUB_REPOSITORY_NAME:-phishint-data-generator}"
BRANCH="${PHISHGEN_INSTALL_BRANCH:-main}"
REPO_URL="${PHISHGEN_REPO_URL:-https://github.com/${OWNER}/${REPOSITORY}.git}"
VERSION="${PHISHGEN_VERSION:-1.0.0}"
RELEASE_TAG="v${VERSION}"
BUNDLE_NAME="phishint-data-generator-images-${VERSION}.tar.gz"
BUNDLE_URL="https://github.com/${OWNER}/${REPOSITORY}/releases/download/${RELEASE_TAG}/${BUNDLE_NAME}"
BUNDLE_SIZE_BYTES="${PHISHGEN_IMAGE_SIZE_BYTES:-1192073169}"
BUNDLE_SHA256="${PHISHGEN_IMAGE_SHA256:-6051a375756346c760c0038ba60fe94c2b2b82923c7b36afd70470b9a97b8f79}"
BACKEND_IMAGE="phishgen_api:${VERSION}"
UI_IMAGE="phishgen_ui:${VERSION}"

if [ -f "${PWD}/docker-compose.yml" ] \
   && [ -f "${PWD}/Dockerfile" ] \
   && [ -f "${PWD}/.env.example" ]; then
  INSTALL_DIR="${PWD}"
else
  INSTALL_DIR="${PHISHGEN_INSTALL_DIR:-${PWD}/${REPOSITORY}}"
fi

DOWNLOAD_ONLY=0
NO_PROMPT=0
NO_INSTALL=0
ASSUME_YES=0
IMAGE_MODE=""
IMAGE_BUNDLE="${PHISHGEN_IMAGE_BUNDLE:-}"

usage() {
  cat <<'EOF'
Install and start the Phishing Data Generator with Docker Compose.

Usage:
  bash install.sh [options]
  curl -fsSL https://raw.githubusercontent.com/VibeATSCoder/phishint-data-generator/main/install.sh | bash

Options:
  --dir PATH          Install into PATH (default: ./phishint-data-generator)
  --branch NAME       Git branch or tag to install (default: main)
  --image PATH        Load the manually downloaded Docker image archive
  --artefact-dir DIR  Find the image archive in DIR
  --manual            Show the browser download link and ask for its path
  --auto-download     Download the prebuilt image archive with curl
  --build             Build images from source instead of using the release
  --download-only     Prepare/load images, but do not start the services
  --no-start          Alias for --download-only
  --no-build          Use prebuilt images (compatibility alias)
  --no-prompt         Do not ask for optional API keys or dependency changes
  --no-install        Never offer to install missing system dependencies
  -y, --yes           Accept dependency and daemon-start prompts
  -h, --help          Show this help

Environment overrides:
  PHISHGEN_INSTALL_DIR, PHISHGEN_INSTALL_BRANCH, PHISHGEN_REPO_URL,
  PHISHGEN_VERSION, PHISHGEN_IMAGE_BUNDLE,
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
    --image)
      [ "$#" -ge 2 ] || { echo "--image needs a path" >&2; exit 2; }
      IMAGE_BUNDLE="$2"; IMAGE_MODE="local"; shift 2 ;;
    --artefact-dir|--artifact-dir)
      [ "$#" -ge 2 ] || { echo "$1 needs a directory" >&2; exit 2; }
      IMAGE_BUNDLE="$2/${BUNDLE_NAME}"; IMAGE_MODE="local"; shift 2 ;;
    --manual) IMAGE_MODE="manual"; shift ;;
    --auto-download) IMAGE_MODE="auto"; shift ;;
    --build) IMAGE_MODE="build"; shift ;;
    --download-only|--no-start) DOWNLOAD_ONLY=1; shift ;;
    --no-build) IMAGE_MODE="prebuilt"; shift ;;
    --no-prompt) NO_PROMPT=1; shift ;;
    --no-install) NO_INSTALL=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Resolve a user-supplied relative archive path before changing into the
# installation directory later in the script.
if [ -n "${IMAGE_BUNDLE}" ] && [ "${IMAGE_BUNDLE#/}" = "${IMAGE_BUNDLE}" ]; then
  IMAGE_BUNDLE="${PWD}/${IMAGE_BUNDLE}"
fi

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
  command -v gzip >/dev/null 2>&1 || missing="${missing} gzip"
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

images_loaded() {
  "${DOCKER[@]}" image inspect "${BACKEND_IMAGE}" >/dev/null 2>&1 \
    && "${DOCKER[@]}" image inspect "${UI_IMAGE}" >/dev/null 2>&1
}

find_bundle() { # optional explicit path -> archive path on stdout
  local candidate="${1:-}" dir
  if [ -n "${candidate}" ]; then
    [ -d "${candidate}" ] && candidate="${candidate%/}/${BUNDLE_NAME}"
    if [ -f "${candidate}" ]; then
      printf '%s' "${candidate}"
      return 0
    fi
  fi
  for dir in "${PWD}" "${HOME:-}/Downloads" "${HOME:-}/downloads" "${HOME:-}"; do
    [ -n "${dir}" ] || continue
    if [ -f "${dir%/}/${BUNDLE_NAME}" ]; then
      printf '%s' "${dir%/}/${BUNDLE_NAME}"
      return 0
    fi
  done
  return 1
}

verify_bundle() { # archive
  local archive="$1" actual="" size=""
  size="$(stat -c%s "${archive}" 2>/dev/null || stat -f%z "${archive}" 2>/dev/null || true)"
  if [ -n "${BUNDLE_SIZE_BYTES}" ] && [ "${size}" != "${BUNDLE_SIZE_BYTES}" ]; then
    die "${archive} is ${size:-an unknown number of} bytes; expected ${BUNDLE_SIZE_BYTES}. Download it again."
  fi
  echo "  checking compressed archive"
  gzip -t "${archive}" || die "${archive} is incomplete or corrupt; download it again"
  echo "  checking SHA-256"
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "${archive}" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "${archive}" | awk '{print $1}')"
  elif command -v openssl >/dev/null 2>&1; then
    actual="$(openssl dgst -sha256 "${archive}" | awk '{print $NF}')"
  else
    die "a SHA-256 tool (sha256sum, shasum, or openssl) is required"
  fi
  [ "${actual}" = "${BUNDLE_SHA256}" ] \
    || die "${archive} has the wrong SHA-256 checksum"
}

ask_for_bundle() {
  local entered="" found=""
  while :; do
    found="$(find_bundle "${IMAGE_BUNDLE}" || true)"
    if [ -n "${found}" ]; then
      IMAGE_BUNDLE="${found}"
      return 0
    fi

    echo
    echo "Download this prebuilt Docker image archive in your browser:"
    echo "  ${BUNDLE_URL}"
    echo
    echo "You may save it anywhere, then paste its full path here."
    echo "Expected filename: ${BUNDLE_NAME}"
    echo "Expected size: 1.11 GiB (${BUNDLE_SIZE_BYTES} bytes)"
    if [ "${HAVE_TTY}" -eq 0 ] || [ "${NO_PROMPT}" -eq 1 ]; then
      die "image archive not found. Download ${BUNDLE_URL}, then rerun with --image /path/to/${BUNDLE_NAME}"
    fi
    entered="$(ask 'Image archive path ([d] download automatically, [b] build locally, [q] quit): ' '' || true)"
    case "${entered}" in
      d|D) IMAGE_MODE="auto"; return 1 ;;
      b|B) IMAGE_MODE="build"; return 1 ;;
      q|Q) die "stopped; rerun after downloading ${BUNDLE_NAME}" ;;
      '') ;;
      *)
        # Paths copied from graphical file managers are sometimes quoted.
        entered="${entered#\"}"; entered="${entered%\"}"
        case "${entered}" in
          '~/'*) entered="${HOME}/${entered#\~/}" ;;
        esac
        IMAGE_BUNDLE="${entered}"
        ;;
    esac
    found="$(find_bundle "${IMAGE_BUNDLE}" || true)"
    if [ -n "${found}" ]; then
      IMAGE_BUNDLE="${found}"
      return 0
    fi
    echo "  file not found yet; check the path and filename"
  done
}

download_bundle() {
  local partial="${INSTALL_DIR}/${BUNDLE_NAME}.part"
  IMAGE_BUNDLE="${INSTALL_DIR}/${BUNDLE_NAME}"
  if [ -f "${IMAGE_BUNDLE}" ]; then
    echo "  using ${IMAGE_BUNDLE}"
    return 0
  fi
  step "downloading prebuilt images"
  echo "  ${BUNDLE_URL}"
  curl -fL --progress-bar --retry 3 --connect-timeout 15 --max-time 7200 \
    -C - -o "${partial}" "${BUNDLE_URL}" \
    || die "image download failed; use --manual to download it in your browser"
  mv "${partial}" "${IMAGE_BUNDLE}"
}

choose_image_mode() {
  local choice=""
  if [ "${IMAGE_MODE}" = "build" ]; then
    return 0
  fi
  if images_loaded; then
    IMAGE_MODE="loaded"
    echo "  prebuilt images ${VERSION} are already loaded"
    return 0
  fi
  if [ "${IMAGE_MODE}" = "local" ]; then
    return 0
  fi
  if [ "${IMAGE_MODE}" = "prebuilt" ]; then
    if [ "${NO_PROMPT}" -eq 1 ] || [ "${HAVE_TTY}" -eq 0 ]; then
      IMAGE_MODE="auto"
    else
      IMAGE_MODE="manual"
    fi
    return 0
  fi
  if [ -n "${IMAGE_MODE}" ]; then
    return 0
  fi
  if [ "${NO_PROMPT}" -eq 1 ] || [ "${HAVE_TTY}" -eq 0 ]; then
    IMAGE_MODE="auto"
    return 0
  fi

  echo
  echo "How should the ready-to-run Docker images be provided?"
  echo "  1) Download in my browser and paste the file path (recommended)"
  echo "  2) Let this installer download the image archive"
  echo "  3) Build locally (downloads requirements, Chromium, and base images)"
  choice="$(ask 'Choice [1]: ' 1 || true)"
  case "${choice}" in
    2) IMAGE_MODE="auto" ;;
    3) IMAGE_MODE="build" ;;
    *) IMAGE_MODE="manual" ;;
  esac
}

prepare_images() {
  local found=""
  step "Docker images"
  choose_image_mode
  case "${IMAGE_MODE}" in
    loaded) return 0 ;;
    build)
      echo "  local source build selected"
      return 0
      ;;
    auto) download_bundle ;;
    local)
      found="$(find_bundle "${IMAGE_BUNDLE}" || true)"
      [ -n "${found}" ] \
        || die "image archive not found at ${IMAGE_BUNDLE}"
      IMAGE_BUNDLE="${found}"
      ;;
    manual)
      if ! ask_for_bundle; then
        case "${IMAGE_MODE}" in
          auto) download_bundle ;;
          build) return 0 ;;
          *) die "no image archive was provided" ;;
        esac
      fi
      ;;
    *) die "unsupported image mode: ${IMAGE_MODE}" ;;
  esac

  [ "${IMAGE_MODE}" = "build" ] && return 0
  verify_bundle "${IMAGE_BUNDLE}"
  echo "  loading image layers; this can take a few minutes"
  "${DOCKER[@]}" load -i "${IMAGE_BUNDLE}" \
    || die "Docker could not load ${IMAGE_BUNDLE}"
  images_loaded \
    || die "the archive did not contain ${BACKEND_IMAGE} and ${UI_IMAGE}"
  echo "  loaded ${BACKEND_IMAGE}"
  echo "  loaded ${UI_IMAGE}"
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
prepare_docker
check_disk_space
prepare_images
set_env_value PHISHGEN_VERSION "${VERSION}"

if [ "${DOWNLOAD_ONLY}" -eq 1 ]; then
  echo
  if [ "${IMAGE_MODE}" = "build" ]; then
    echo "Source and configuration are ready in ${INSTALL_DIR}."
    echo "Build and start later with:"
    echo "  cd '${INSTALL_DIR}' && docker compose up --build -d"
  else
    echo "Source, configuration, and prebuilt images are ready in ${INSTALL_DIR}."
    echo "Start later with:"
    echo "  cd '${INSTALL_DIR}' && docker compose -f docker-compose.images.yml up -d"
  fi
  exit 0
fi

step "validating Compose configuration"
if [ "${IMAGE_MODE}" = "build" ]; then
  "${DOCKER[@]}" compose -f docker-compose.yml config --quiet \
    || die "docker-compose.yml or .env is invalid"
else
  "${DOCKER[@]}" compose -f docker-compose.images.yml config --quiet \
    || die "docker-compose.images.yml or .env is invalid"
fi

step "starting services"
if [ "${IMAGE_MODE}" = "build" ]; then
  "${DOCKER[@]}" compose -f docker-compose.yml up --build -d
else
  "${DOCKER[@]}" compose -f docker-compose.images.yml up -d
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
if [ "${IMAGE_MODE}" = "build" ]; then
  echo "  docker compose ps"
  echo "  docker compose logs -f"
  echo "  docker compose down"
else
  echo "  docker compose -f docker-compose.images.yml ps"
  echo "  docker compose -f docker-compose.images.yml logs -f"
  echo "  docker compose -f docker-compose.images.yml down"
fi

} # end parse-before-execute block
