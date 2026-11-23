echo "Ubuntu packages"
while IFS= read -r package; do
  package_info=$(dpkg-query -W -f='${db:Status-Status} ${Version}' "$package" 2>/dev/null || true)
  case "$package_info" in
    'installed '*) printf '%s %s\n' "$package" "${package_info#installed }" ;;
    *) printf '%s missing\n' "$package" ;;
  esac
done < "$PC_SETUP_REPO_PATH/os/ubuntu/apt-packages.txt"

echo
print_version "Docker Compose" docker compose version
print_version "Docker Buildx" docker buildx version
for service in docker.service containerd.service; do
  printf '%s: active=%s enabled=%s\n' "$service" \
    "$(systemctl is-active "$service" 2>/dev/null || true)" \
    "$(systemctl is-enabled "$service" 2>/dev/null || true)"
done
