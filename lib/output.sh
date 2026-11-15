#!/bin/zsh

OUTPUT_TAG="[pc-setup]"

log() {
  echo "🔧 $OUTPUT_TAG $1"
}

success() {
  echo "✅ $OUTPUT_TAG $1"
}

error() {
  echo "⚠️ $OUTPUT_TAG $1"
}

note() {
  echo "🔧 $OUTPUT_TAG $1"
}
