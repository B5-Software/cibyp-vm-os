#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build-time only. Never download or install an IDE from the App at runtime.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
case "$(dpkg --print-architecture)" in
  amd64) architecture=x64 ;;
  arm64) architecture=arm64 ;;
  *) echo 'Unsupported Code-OSS server architecture' >&2; exit 1 ;;
esac
commit="$(jq -er .commit "$here/runtime-lock.json")"
asset="linux-$architecture"
url="$(jq -er --arg key "$asset" '.remote[$key].url' "$here/runtime-lock.json")"
sha="$(jq -er --arg key "$asset" '.remote[$key].sha256' "$here/runtime-lock.json")"
root=/usr/local/lib/cibyp-codeoss
install -d -m 0755 "$root"
scratch="$(mktemp -d "$root/.build-XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
curl --fail --location --retry 5 --proto '=https' --tlsv1.2 "$url" -o "$scratch/runtime.tar.gz"
printf '%s  %s\n' "$sha" "$scratch/runtime.tar.gz" | sha256sum --check --status
mkdir "$scratch/app"
tar -xzf "$scratch/runtime.tar.gz" -C "$scratch/app" --no-same-owner
test "$(jq -er .commit "$scratch/app/product.json")" = "$commit"
test -x "$scratch/app/node"
test -f "$scratch/app/out/server-main.js"
test -d "$scratch/app/extensions/git"
cp "$here/runtime-lock.json" "$scratch/app/cibyp-runtime.json"
chmod -R go-w "$scratch/app"
if [ ! -d "$root/$commit" ]; then mv "$scratch/app" "$root/$commit"; fi
ln -sfn "$commit" "$root/current"
install -m 0755 "$here/server.py" /usr/local/bin/cibyp-codeoss-server
echo "[cibyp] Code-OSS remote extension host $commit ($architecture) installed in image"
