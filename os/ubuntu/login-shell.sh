get_login_shell() {
  getent passwd "$(id -un)" | cut -d: -f7
}
