if command -v docker >/dev/null 2>&1; then
  check_command "Docker daemon" docker info
  check_command "Docker Compose" docker compose version
else
  note "Docker Engine and Compose are optional."
fi
