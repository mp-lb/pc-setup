#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT
test_home="$test_root/home"
test_repo="$test_root/work space/pc-setup"
mkdir -p "$test_home/.local/bin" "$test_home/.local/share/mise/shims" \
  "$test_home/.local/share/npm-global/bin" "$(dirname "$test_repo")"
ln -s "$REPO" "$test_repo"

# Stub the activation interface so these tests require no downloaded runtimes.
cat > "$test_home/.local/bin/mise" <<'MISE'
#!/bin/sh
case "$*" in
  'activate zsh --shims') printf 'export PATH="$HOME/.local/share/mise/shims:$PATH"\n' ;;
  'activate zsh') printf 'export TEST_INTERACTIVE_MISE=1\n' ;;
  *) exit 1 ;;
esac
MISE
printf '#!/bin/sh\nprintf "test-node\\n"\n' > "$test_home/.local/share/mise/shims/node"
printf '#!/bin/sh\nexec node\n' > "$test_home/.local/share/npm-global/bin/fm"
chmod +x "$test_home/.local/bin/mise" "$test_home/.local/share/mise/shims/node" \
  "$test_home/.local/share/npm-global/bin/fm"

install_bridges() {
  env -i HOME="$test_home" ZDOTDIR="$dotdir" PATH=/usr/bin:/bin \
    PC_SETUP_REPO_PATH="$test_repo" /bin/bash "$REPO/bin/install-shell"
}

for dotdir in "$test_home" "$test_home/custom zsh"; do
  mkdir -p "$dotdir"
  printf 'export TEST_EXISTING_ENV=preserved\n' > "$dotdir/.zshenv"
  printf 'export TEST_INTERACTIVE_RC=1\n' > "$dotdir/.zshrc"
  install_bridges
  cp "$dotdir/.zshenv" "$test_root/expected-env"
  cp "$dotdir/.zshrc" "$test_root/expected-rc"
  install_bridges
  cmp "$dotdir/.zshenv" "$test_root/expected-env"
  cmp "$dotdir/.zshrc" "$test_root/expected-rc"

  for mode in -c -lc; do
    output=$(env -i HOME="$test_home" ZDOTDIR="$dotdir" PATH=/usr/bin:/bin /bin/zsh "$mode" '
      [[ "$TEST_EXISTING_ENV" == preserved && -z "$TEST_INTERACTIVE_RC" && -z "$TEST_INTERACTIVE_MISE" ]] || exit 1
      [[ "$(command -v node)" == "$HOME/.local/share/mise/shims/node" ]] || exit 1
      [[ "$(command -v fm)" == "$HOME/.local/share/npm-global/bin/fm" ]] || exit 1
      command -v install-shell >/dev/null || exit 1
      original_path=$PATH
      source "$PC_SETUP_REPO_PATH/env/zshenv"
      [[ "$PATH" == "$original_path" ]] || exit 1
      [[ "$(node)" == test-node && "$(fm)" == test-node ]] || exit 1
    ' 2>&1)
    [[ -z "$output" ]] || { printf 'Unexpected shell output: %s\n' "$output"; exit 1; }
  done

  env -i HOME="$test_home" ZDOTDIR="$dotdir" PATH=/usr/bin:/bin TERM=dumb /bin/zsh -ic '
    [[ "$TEST_EXISTING_ENV" == preserved && "$TEST_INTERACTIVE_RC" == 1 && "$TEST_INTERACTIVE_MISE" == 1 ]]
  '
done
printf 'Shell startup tests passed.\n'
