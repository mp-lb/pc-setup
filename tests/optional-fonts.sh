#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT
mkdir -p "$test_root/bin"
export FONT_TEST_ROOT="$test_root"
export PC_SETUP_WORKSPACE="$test_root/work space"
export PATH="$test_root/bin:$PATH"

cat > "$test_root/bin/gh" <<'STUB'
#!/bin/bash
set -euo pipefail
case "$1 $2" in
  'api repos/felixsebastian/ubuntu-fonts')
    [ "${FONT_TEST_ACCESS:-no}" = yes ] || { echo 'Not Found' >&2; exit 1; }
    echo true
    ;;
  'repo clone')
    [ "$3" = felixsebastian/ubuntu-fonts ]
    mkdir -p "$4"
    printf '%s\n' '#!/bin/bash' 'touch "$FONT_TEST_ROOT/installed"' > "$4/install.sh"
    touch "$FONT_TEST_ROOT/cloned"
    ;;
  *) exit 99 ;;
esac
STUB
cat > "$test_root/bin/git" <<'STUB'
#!/bin/bash
set -euo pipefail
[ "$1" = -C ]
[ "$2" = "$PC_SETUP_WORKSPACE/ubuntu-fonts" ]
case "$3 $4" in
  'remote get-url') echo "${FONT_TEST_ORIGIN:-https://github.com/felixsebastian/ubuntu-fonts.git}" ;;
  'status --porcelain') printf '%s' "${FONT_TEST_DIRTY:-}" ;;
  'pull --ff-only') touch "$FONT_TEST_ROOT/pulled" ;;
  *) exit 99 ;;
esac
STUB
chmod +x "$test_root/bin/gh" "$test_root/bin/git"

# No access must succeed silently, without creating a checkout or installing.
bash "$REPO/os/ubuntu/install-optional-fonts.sh" > "$test_root/output" 2>&1
[ ! -s "$test_root/output" ]
[ ! -e "$PC_SETUP_WORKSPACE" ]
[ ! -e "$test_root/installed" ]

# Access enables a first clone and subsequent fast-forward updates.
export FONT_TEST_ACCESS=yes
bash "$REPO/os/ubuntu/install-optional-fonts.sh"
[ -f "$test_root/cloned" ] && [ -f "$test_root/installed" ]
rm "$test_root/installed"
bash "$REPO/os/ubuntu/install-optional-fonts.sh"
[ -f "$test_root/pulled" ] && [ -f "$test_root/installed" ]
rm "$test_root/pulled" "$test_root/installed"

# Never update or execute a dirty checkout or an unrelated repository.
export FONT_TEST_DIRTY=' M install.sh'
if bash "$REPO/os/ubuntu/install-optional-fonts.sh" > "$test_root/output" 2>&1; then exit 1; fi
[ ! -e "$test_root/pulled" ] && [ ! -e "$test_root/installed" ]
unset FONT_TEST_DIRTY
export FONT_TEST_ORIGIN=https://github.com/example/unrelated.git
if bash "$REPO/os/ubuntu/install-optional-fonts.sh" > "$test_root/output" 2>&1; then exit 1; fi
[ ! -e "$test_root/pulled" ] && [ ! -e "$test_root/installed" ]
unset FONT_TEST_ORIGIN

# An accessible installer's failure must be visible to the calling setup.
printf '%s\n' '#!/bin/bash' 'exit 42' > "$PC_SETUP_WORKSPACE/ubuntu-fonts/install.sh"
result=0
bash "$REPO/os/ubuntu/install-optional-fonts.sh" || result=$?
[ "$result" -eq 42 ]
printf 'Optional font setup tests passed.\n'
