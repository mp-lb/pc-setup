check_command "Vim" vim --version
check_command "Docker CLI" docker --version
check_command "Docker daemon (local socket access)" docker --host unix:///var/run/docker.sock info
check_command "Docker Compose" docker compose version
check_command "Docker Buildx" docker buildx version
check_command "Docker running" systemctl is-active --quiet docker.service
check_command "Docker enabled at boot" systemctl is-enabled --quiet docker.service
check_command "containerd running" systemctl is-active --quiet containerd.service
check_command "containerd enabled at boot" systemctl is-enabled --quiet containerd.service
