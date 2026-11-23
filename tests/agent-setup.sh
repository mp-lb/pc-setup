#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT
test_home="$test_root/home"
mkdir -p "$test_home/.local/bin"

cat > "$test_home/.local/bin/mise" <<'STUB'
#!/bin/bash
printenv PATH
STUB
cat > "$test_home/.local/bin/fm" <<'STUB'
#!/bin/bash
case "$*" in
  'read agents/global-instructions.md --store mp-lb/mp-lb')
    case "${TEST_FETCH:-ok}" in
      fail) printf 'partial response'; exit 1 ;;
      empty) printf ' \n\t' ;;
      *) printf '# Shared instructions\n\nKeep it simple.\n' ;;
    esac ;;
  'skills / --store mp-lb/skills --agents all --global')
    printf '%s\n' "$*" >> "$HOME/skills-calls"
    [ "${TEST_FETCH:-ok}" != fail ] ;;
  *) exit 1 ;;
esac
STUB
cat > "$test_home/.local/bin/npm" <<'STUB'
#!/bin/bash
exit 0
STUB
cat > "$test_home/.local/bin/npx" <<'STUB'
#!/bin/bash
printf '%s\n' "$*" >> "$HOME/skills-calls"
STUB
chmod +x "$test_home/.local/bin/"*

run_installer() {
  env -i HOME="$test_home" PATH=/usr/bin:/bin PC_SETUP_REPO_PATH="$REPO" \
    TEST_FETCH="${fetch_mode:-ok}" /bin/bash "$REPO/bin/$1"
}

run_installer install-global-instructions
printf '# Shared instructions\n\nKeep it simple.\n' > "$test_root/expected"
for fetch_mode in ok fail empty; do
  if [ "$fetch_mode" = ok ]; then
    run_installer install-global-instructions
  elif run_installer install-global-instructions; then
    echo "Expected $fetch_mode fetch to fail" >&2
    exit 1
  fi
  cmp "$test_root/expected" "$test_home/.codex/AGENTS.md"
  cmp "$test_root/expected" "$test_home/.claude/CLAUDE.md"
done

fetch_mode=ok
run_installer install-skills
grep -Fxq 'skills / --store mp-lb/skills --agents all --global' "$test_home/skills-calls"
grep -Fq -- '--global --agent codex claude-code --skill * --yes' "$test_home/skills-calls"
rm "$test_home/skills-calls"
fetch_mode=fail
if run_installer install-skills; then
  echo 'Expected Forum skill installation failure to propagate' >&2
  exit 1
fi
[ "$(wc -l < "$test_home/skills-calls" | tr -d ' ')" = 1 ]
printf 'Agent setup tests passed.\n'
