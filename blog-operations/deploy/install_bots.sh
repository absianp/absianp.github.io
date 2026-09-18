#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unit_dir="${HOME}/.config/systemd/user"
mkdir -p "$unit_dir"
install -m 644 "$script_dir/blog-ops-bot@.service" "$unit_dir/blog-ops-bot@.service"
systemctl --user daemon-reload
systemctl --user enable --now blog-ops-bot@absian.service blog-ops-bot@goldenlife.service blog-ops-bot@kpop.service
