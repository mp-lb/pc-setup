echo "Ubuntu packages"
while IFS= read -r package; do
  package_info=$(dpkg-query -W -f='${db:Status-Status} ${Version}' "$package" 2>/dev/null || true)
  case "$package_info" in
    'installed '*) printf '%s %s\n' "$package" "${package_info#installed }" ;;
    *) printf '%s missing\n' "$package" ;;
  esac
done < "$PC_SETUP_REPO_PATH/os/ubuntu/apt-packages.txt"
