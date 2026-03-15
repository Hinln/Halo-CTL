#!/usr/bin/env bash
set -euo pipefail

SCRIPT_VERSION="1.0.2-beta"

REPO_OWNER="Hinln"
REPO_NAME="Halo-CTL"
IMAGE="ghcr.io/hinln/halo-ctl:latest"

APP_DIR="${HOME}/${REPO_NAME}"
ENV_FILE="${APP_DIR}/.env"

NETWORK_NAME="openclaw-net"
AGENT_ALIAS="agent"

DEPLOY_MODE=""
PROMPT_INPUT=""

LOG_FILE="${LOG_FILE:-/var/log/docker_deploy.log}"
LOG_LEVEL="INFO"
ASSUME_YES="0"
DRY_RUN="0"
RECONFIGURE="0"

require_cmd() {
  command -v "$1" >/dev/null 2>&1
}

now_ts() {
  date "+%Y-%m-%dT%H:%M:%S%z"
}

level_rank() {
  case "$1" in
    DEBUG) echo 10 ;;
    INFO) echo 20 ;;
    WARN) echo 30 ;;
    ERROR) echo 40 ;;
    *) echo 20 ;;
  esac
}

can_log() {
  [[ $(level_rank "$1") -ge $(level_rank "$LOG_LEVEL") ]]
}

ensure_log_file() {
  if [[ -w "$(dirname "$LOG_FILE")" ]]; then
    :
  else
    if require_cmd sudo; then
      sudo mkdir -p "$(dirname "$LOG_FILE")"
      sudo touch "$LOG_FILE"
      sudo chmod 600 "$LOG_FILE"
    else
      echo "Cannot write $LOG_FILE and sudo not available" >&2
      exit 1
    fi
  fi
}

write_log_line() {
  local lvl="$1"
  local msg="$2"
  local line
  line="$(now_ts) [$lvl] $msg"
  if [[ -w "$LOG_FILE" ]]; then
    printf '%s\n' "$line" >>"$LOG_FILE"
  else
    sudo sh -lc "printf '%s\\n' \"$line\" >> '$LOG_FILE'"
  fi
}

log() {
  local lvl="$1"
  shift
  local msg="$*"
  if can_log "$lvl"; then
    printf '%s\n' "$(now_ts) [$lvl] $msg"
  fi
  write_log_line "$lvl" "$msg"
}

run_cmd() {
  local cmd="$*"
  log DEBUG "cmd: $cmd"
  if [[ "$DRY_RUN" == "1" ]]; then
    log INFO "dry-run: $cmd"
    return 0
  fi
  local out
  if ! out=$(eval "$cmd" 2>&1); then
    log ERROR "failed: $cmd"
    log ERROR "output: $out"
    return 1
  fi
  if [[ -n "$out" ]]; then
    log DEBUG "output: $out"
  fi
  return 0
}

usage() {
  cat <<EOF
Usage: deploy.sh [options]

Options:
  -h, --help        Show help
  -y, --yes         Skip confirmations
  -v, --verbose     Enable DEBUG logs
  --dry-run         Print actions without changes
  --reconfigure     Force reconfigure and rewrite .env

Environment:
  REPO_OWNER, REPO_NAME, IMAGE, NETWORK_NAME, LOG_FILE
  HALOCTL_PROMPT_STDIN=1 (force reading prompts from stdin; for tests only)
EOF
}

init_prompt_input() {
  if [[ "${HALOCTL_PROMPT_STDIN:-}" == "1" ]]; then
    PROMPT_INPUT="/dev/stdin"
    return 0
  fi
  if [[ -t 0 ]]; then
    PROMPT_INPUT="/dev/stdin"
    return 0
  fi
  if [[ -r /dev/tty ]]; then
    PROMPT_INPUT="/dev/tty"
    return 0
  fi
  PROMPT_INPUT="/dev/stdin"
}

die() {
  log ERROR "$*"
  exit 1
}

on_exit() {
  local code="$1"
  if [[ "$code" == "0" ]]; then
    return 0
  fi
  log ERROR "脚本异常终止（exit=$code）。如果你通过 \"curl ... | bash\" 运行，请改用交互式执行：\n  curl -sSL https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/deploy.sh -o deploy.sh && bash deploy.sh\n\nScript aborted (exit=$code). If you ran via \"curl ... | bash\", run interactively instead."
}

trap 'on_exit $?' EXIT

is_valid_url() {
  local u="$1"
  [[ "$u" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]+)?(/.*)?$ ]]
}

is_valid_pat() {
  local p="$1"
  [[ -n "$p" ]] || return 1
  if [[ "$p" =~ ^pat_[A-Za-z0-9_\-]{6,}$ ]]; then
    return 0
  fi
  return 0
}

write_env_file() {
  local base_url="$1"
  local pat="$2"
  local timeout_s="$3"
  local debug="$4"

  umask 177
  cat > "$ENV_FILE" <<EOF
HALO_BASE_URL=${base_url}
HALO_PAT=${pat}
HALO_TIMEOUT_S=${timeout_s}
HALO_DEBUG=${debug}
NETWORK_NAME=${NETWORK_NAME}
IMAGE=${IMAGE}
EOF
  chmod 600 "$ENV_FILE"
}

verify_config_with_api() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log INFO "dry-run: skip API validation"
    return 0
  fi
  log INFO "验证 Halo 地址与 PAT 可用性（whoami）/ validating Halo base URL & PAT (whoami)"
  if docker compose run --rm halo-cli whoami >/dev/null 2>&1; then
    log INFO "验证通过 / validation OK"
    return 0
  fi
  log WARN "验证失败：请检查 Halo 地址/PAT 或网络 / validation failed: check base URL, PAT, or network"
  return 1
}

detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "${ID:-unknown}"
    return
  fi
  echo "unknown"
}

install_docker_ubuntu_debian() {
  run_cmd "sudo apt-get update"
  run_cmd "sudo apt-get install -y ca-certificates curl gnupg"
  run_cmd "sudo install -m 0755 -d /etc/apt/keyrings"
  run_cmd "curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo \"$ID\")/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
  run_cmd "sudo chmod a+r /etc/apt/keyrings/docker.gpg"
  run_cmd "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo \"$ID\") $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable\" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null"
  run_cmd "sudo apt-get update"
  run_cmd "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
}

install_docker_centos() {
  run_cmd "sudo dnf -y install dnf-plugins-core"
  run_cmd "sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo"
  run_cmd "sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
  run_cmd "sudo systemctl enable --now docker"
}

prompt() {
  local var_name="$1"
  local label="$2"
  local secret="${3:-0}"
  local default_value="${4:-}"
  local value=""
  if [[ "$secret" == "1" ]]; then
    if ! IFS= read -r -s -p "${label}: " value <"$PROMPT_INPUT"; then
      echo
      die "无法读取交互输入（stdin 非 TTY）。请改用：bash deploy.sh\nCannot read interactive input (stdin is not a TTY). Please run: bash deploy.sh"
    fi
    echo
  else
    if [[ -n "$default_value" ]]; then
      if ! IFS= read -r -p "${label} [${default_value}]: " value <"$PROMPT_INPUT"; then
        die "无法读取交互输入（stdin 非 TTY）。请改用：bash deploy.sh\nCannot read interactive input (stdin is not a TTY). Please run: bash deploy.sh"
      fi
      value="${value:-$default_value}"
    else
      if ! IFS= read -r -p "${label}: " value <"$PROMPT_INPUT"; then
        die "无法读取交互输入（stdin 非 TTY）。请改用：bash deploy.sh\nCannot read interactive input (stdin is not a TTY). Please run: bash deploy.sh"
      fi
    fi
  fi
  printf -v "$var_name" "%s" "$value"
}

confirm() {
  local question="$1"
  if [[ "$ASSUME_YES" == "1" ]]; then
    return 0
  fi
  local ans
  if ! IFS= read -r -p "$question [y/N]: " ans <"$PROMPT_INPUT"; then
    return 1
  fi
  case "${ans:-}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

trim_slash() {
  local s="$1"
  s="${s%/}"
  echo "$s"
}

join_url() {
  local base
  base=$(trim_slash "$1")
  local path="$2"
  path="${path#/}"
  echo "${base}/${path}"
}

detect_local_halo_container() {
  local listing="$1"
  if echo "$listing" | grep -Ei '\bhalo\b|/halo|halo:' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

verify_remote_halo_reachable() {
  local base_url="$1"
  local url
  url=$(join_url "$base_url" "/apis/api.console.halo.run/v1alpha1/users/-")

  local tries=0
  while [[ $tries -lt 3 ]]; do
    tries=$((tries + 1))
    log INFO "远程模式：验证域名可达性（${tries}/3）/ remote: verifying reachability (${tries}/3)"
    if [[ "$DRY_RUN" == "1" ]]; then
      log INFO "dry-run: skip reachability check"
      return 0
    fi
    local code
    code=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 10 "$url" || echo "000")
    if [[ "$code" == "401" || "$code" == "403" || "$code" == "200" ]]; then
      log INFO "域名可达且 API 路径存在（HTTP $code）/ reachable and API path exists (HTTP $code)"
      return 0
    fi
    log WARN "验证失败（HTTP $code）：$url"
    sleep 1
  done
  return 1
}

scan_containers() {
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
}

print_container_list() {
  local idx=1
  while IFS=$'\t' read -r name image status ports; do
    printf '%2d) %-28s %-34s %-18s %s\n' "$idx" "$name" "$image" "${status:0:16}" "$ports"
    idx=$((idx + 1))
  done
}

resolve_selection() {
  local selection="$1"
  local names
  names=$(scan_containers | cut -f1)
  if [[ "$selection" =~ ^[0-9]+$ ]]; then
    echo "$names" | sed -n "${selection}p"
    return
  fi
  if echo "$names" | grep -qx "$selection"; then
    echo "$selection"
    return
  fi
  echo ""
}

container_running() {
  local name="$1"
  docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null | grep -qx true
}

container_network_mode() {
  docker inspect -f '{{.HostConfig.NetworkMode}}' "$1" 2>/dev/null || true
}

container_networks() {
  docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$1" 2>/dev/null || true
}

network_exists() {
  docker network ls --format '{{.Name}}' | grep -qx "$1"
}

container_on_network() {
  local container="$1"
  local net="$2"
  docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$container" | tr ' ' '\n' | grep -qx "$net"
}

deploy_compose() {
  mkdir -p "$APP_DIR"
  cd "$APP_DIR"

  run_cmd "curl -fsSL https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main/docker-compose.yml -o docker-compose.yml"

  local has_existing="0"
  if [[ -f "$ENV_FILE" && "$RECONFIGURE" != "1" ]]; then
    has_existing="1"
    log INFO "检测到已有配置文件：$ENV_FILE"
    if confirm "检测到已有 .env，是否复用现有配置？/ Reuse existing .env?"; then
      log INFO "复用现有配置 / reuse existing config"
    else
      RECONFIGURE="1"
    fi
  fi

  if [[ "$has_existing" != "1" || "$RECONFIGURE" == "1" ]]; then
    local base_url pat timeout_s debug
    while true; do
      prompt base_url "Halo 博客地址（例如 https://your-halo.example）/ Halo base URL" 0 "${HALO_BASE_URL:-}"
      if is_valid_url "$base_url"; then
        break
      fi
      log WARN "地址格式不正确：必须以 http(s):// 开头 / invalid URL format"
    done

    while true; do
      prompt pat "Halo API 密钥（PAT）/ Halo PAT" 1 ""
      if is_valid_pat "$pat"; then
        break
      fi
      log WARN "PAT 格式不正确 / invalid PAT"
    done

    prompt timeout_s "请求超时秒数 / request timeout seconds" 0 "120"
    prompt debug "启用调试日志 HALO_DEBUG（0/1）" 0 "0"

    write_env_file "$base_url" "$pat" "$timeout_s" "$debug"
    log INFO "已写入配置文件：$ENV_FILE（权限 600）/ wrote .env (chmod 600)"
  fi

  run_cmd "docker pull ${IMAGE}"

  local attempts=0
  while [[ $attempts -lt 3 ]]; do
    if verify_config_with_api; then
      break
    fi
    attempts=$((attempts + 1))
    if [[ $attempts -ge 3 ]]; then
      log ERROR "多次验证失败，请手动检查配置后重试 / validation failed too many times"
      return 1
    fi
    log INFO "重新配置（仅更新 Halo 地址与 PAT）/ reconfigure base URL & PAT"
    local base_url pat
    while true; do
      prompt base_url "Halo 博客地址（例如 https://your-halo.example）/ Halo base URL" 0 ""
      if is_valid_url "$base_url"; then
        break
      fi
      log WARN "地址格式不正确：必须以 http(s):// 开头 / invalid URL format"
    done
    while true; do
      prompt pat "Halo API 密钥（PAT）/ Halo PAT" 1 ""
      if is_valid_pat "$pat"; then
        break
      fi
      log WARN "PAT 格式不正确 / invalid PAT"
    done
    local timeout_s debug
    timeout_s=$(grep -E '^HALO_TIMEOUT_S=' "$ENV_FILE" | head -n 1 | cut -d= -f2- || echo "120")
    debug=$(grep -E '^HALO_DEBUG=' "$ENV_FILE" | head -n 1 | cut -d= -f2- || echo "0")
    write_env_file "$base_url" "$pat" "$timeout_s" "$debug"
  done

  log INFO "PAT 权限探针（只读）/ PAT probe (read-only)"
  run_cmd "docker compose run --rm halo-cli pat-probe" || true
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      -y|--yes)
        ASSUME_YES="1"
        shift
        ;;
      -v|--verbose)
        LOG_LEVEL="DEBUG"
        shift
        ;;
      --dry-run)
        DRY_RUN="1"
        shift
        ;;
      --reconfigure)
        RECONFIGURE="1"
        shift
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage
        exit 2
        ;;
    esac
  done

  init_prompt_input

  ensure_log_file
  log INFO "start deploy (version=${SCRIPT_VERSION})"

  local os_id
  os_id=$(detect_os)
  if ! require_cmd docker; then
    log WARN "docker not found, installing"
    case "$os_id" in
      ubuntu|debian) install_docker_ubuntu_debian ;;
      centos|rhel|rocky|almalinux) install_docker_centos ;;
      *)
        log ERROR "unsupported os for auto-install: $os_id"
        exit 1
        ;;
    esac
  fi

  if ! docker compose version >/dev/null 2>&1; then
    log ERROR "docker compose plugin not found"
    exit 1
  fi

  log INFO "scan running containers"
  local listing
  listing=$(scan_containers || true)

  if [[ -z "$listing" ]]; then
    log WARN "未检测到本机运行容器，将切换为远程公网模式 / no local containers found, switch to remote mode"
    DEPLOY_MODE="remote"
  else
    printf '%s\n' "$listing" | print_container_list
    if ! detect_local_halo_container "$listing"; then
      log WARN "未检测到 Halo 相关容器（name/image 不含 halo）。若 Halo 不在本机，可切换到远程公网模式。"
    fi
    DEPLOY_MODE="local"
  fi

  local selected_container=""
  local created_network="0"
  local connected_agent="0"

  if [[ "$DEPLOY_MODE" == "local" ]]; then
    local selected_input
    while true; do
      prompt selected_input "选择 Agent 容器（输入编号/容器名；或输入 r 切换远程模式）/ Select agent container (number/name; or r for remote)" 0 "1"
      if [[ "$selected_input" == "r" || "$selected_input" == "R" ]]; then
        DEPLOY_MODE="remote"
        break
      fi
      selected_container=$(resolve_selection "$selected_input")
      if [[ -z "$selected_container" ]]; then
        log WARN "invalid selection: $selected_input"
        continue
      fi
      if ! container_running "$selected_container"; then
        log WARN "container not running: $selected_container"
        continue
      fi
      local mode
      mode=$(container_network_mode "$selected_container")
      if [[ "$mode" == "host" || "$mode" == "none" ]]; then
        log WARN "unsupported network mode for auto-attach: $mode"
        continue
      fi
      break
    done
  fi

  if [[ "$DEPLOY_MODE" == "remote" ]]; then
    log INFO "远程公网模式：将跳过本地容器选择与网络接入 / remote mode: skip local container selection & network attach"
    local remote_url
    while true; do
      prompt remote_url "请输入 Halo 站点公网域名（例如 https://blog.example.com）/ Enter Halo public URL" 0 "${HALO_BASE_URL:-}"
      if is_valid_url "$remote_url"; then
        if verify_remote_halo_reachable "$remote_url"; then
          export HALO_BASE_URL="$remote_url"
          break
        fi
        log WARN "无法验证 Halo API 可达性，请检查域名/网络/HTTPS / cannot verify Halo API reachability"
        continue
      fi
      log WARN "地址格式不正确：必须以 http(s):// 开头 / invalid URL format"
    done

    if ! deploy_compose; then
      die "deploy failed"
    fi
  else
    log INFO "selected agent container: $selected_container"
    if ! confirm "Proceed to attach agent container to network '${NETWORK_NAME}' and deploy tool?"; then
      log INFO "aborted by user"
      exit 0
    fi

    if ! network_exists "$NETWORK_NAME"; then
      log INFO "create network: $NETWORK_NAME"
      run_cmd "docker network create $NETWORK_NAME"
      created_network="1"
    else
      log INFO "reuse network: $NETWORK_NAME"
    fi

    if ! container_on_network "$selected_container" "$NETWORK_NAME"; then
      log INFO "connect agent container to network"
      if run_cmd "docker network connect --alias $AGENT_ALIAS $NETWORK_NAME $selected_container"; then
        connected_agent="1"
        log INFO "connected: $selected_container -> $NETWORK_NAME (alias=$AGENT_ALIAS)"
      else
        log ERROR "failed to connect container to network"
        if [[ "$created_network" == "1" ]]; then
          run_cmd "docker network rm $NETWORK_NAME" || true
        fi
        exit 1
      fi
    else
      log INFO "agent container already on network: $NETWORK_NAME"
    fi

    if ! deploy_compose; then
      log ERROR "deploy failed"
      if [[ "$connected_agent" == "1" ]]; then
        run_cmd "docker network disconnect $NETWORK_NAME $selected_container" || true
      fi
      if [[ "$created_network" == "1" ]]; then
        run_cmd "docker network rm $NETWORK_NAME" || true
      fi
      exit 1
    fi
  fi

  log INFO "done"
  echo "Ready. Example commands:"
  echo "  cd ${APP_DIR}"
  echo "  docker compose run --rm halo-cli whoami"
  echo "  docker compose run --rm halo-cli publish-json --file ./payload.json"
  echo "Log file: ${LOG_FILE}"
}

main "$@"
