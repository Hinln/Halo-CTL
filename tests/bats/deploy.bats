#!/usr/bin/env bats

setup() {
  export PATH="$BATS_TEST_DIRNAME/mocks:$PATH"
  export HOME="$BATS_TEST_DIRNAME/tmp"
  mkdir -p "$HOME"
  export REPO_OWNER="x"
  export REPO_NAME="y"
  export IMAGE="ghcr.io/x/y:latest"
  export LOG_FILE="$HOME/docker_deploy.log"
  export HALOCTL_PROMPT_STDIN=1
}

@test "--help exits 0" {
  run bash "$BATS_TEST_DIRNAME/../../deploy.sh" --help
  [ "$status" -eq 0 ]
}

@test "--dry-run lists containers and completes" {
  run bash "$BATS_TEST_DIRNAME/../../deploy.sh" --dry-run --yes <<< $'1\nhttps://example.com\npat_x\n120\n0\n'
  [ "$status" -eq 0 ]
  [[ "$output" == *"scan running containers"* ]]
}


@test "writes .env and validates whoami" {
  run bash "$BATS_TEST_DIRNAME/../../deploy.sh" --yes <<< $'1\nhttps://example.com\npat_x\n120\n0\n'
  [ "$status" -eq 0 ]
  [ -f "$HOME/y/.env" ]
}


@test "remote mode when no local containers" {
  export MOCK_DOCKER_EMPTY=1
  run bash "$BATS_TEST_DIRNAME/../../deploy.sh" --dry-run --yes <<< $'https://blog.example.com\n\npat_x\n120\n0\n'
  [ "$status" -eq 0 ]
  [ -f "$HOME/y/.env" ]
}
