get_login_shell() {
  dscl . -read "/Users/$(id -un)" UserShell | awk '{print $2}'
}
