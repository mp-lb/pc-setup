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

# Use a real terminal to verify startup cwd without redirecting command jobs.
python3 - "$test_home" "$test_root" "$REPO" <<'PYTHON'
import errno
import os
import pty
import sys

home, start_dir, repo = sys.argv[1:]
workspace = os.path.join(start_dir, 'work space')
dotdir = os.path.join(start_dir, 'terminal-zsh')
os.mkdir(dotdir)
with open(os.path.join(dotdir, '.zshrc'), 'w') as rc:
    rc.write('source "$PC_SETUP_REPO_PATH/env/zshrc"\n')
for args, target in [([], workspace), (['-l'], workspace),
                     (['-c', 'print -r -- "START_DIR=$PWD"'], workspace),
                     ([], os.path.join(start_dir, 'missing'))]:
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(start_dir)
        os.execve('/bin/zsh', ['zsh', '-i', *args], {
            'HOME': home, 'PATH': '/usr/bin:/bin', 'TERM': 'dumb',
            'PC_SETUP_WORKSPACE': target, 'PC_SETUP_REPO_PATH': repo,
            'ZDOTDIR': dotdir,
        })
    if '-c' not in args:
        os.write(fd, b'print -r -- "START_DIR=$PWD"\nexit\n')
    output = b''
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError as error:
            if error.errno != errno.EIO:
                raise
            break
        if not chunk:
            break
        output += chunk
    os.close(fd)
    _, status = os.waitpid(pid, 0)
    expected = (target if sys.platform.startswith('linux') and '-c' not in args
                and os.path.isdir(target) else start_dir)
    assert status == 0 and f'START_DIR={expected}\r\n'.encode() in output, output
PYTHON
printf 'Shell startup tests passed.\n'
