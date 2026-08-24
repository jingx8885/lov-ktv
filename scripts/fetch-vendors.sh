#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"

clone() {
  local url="$1"
  local dir="$2"
  local dest="$VENDOR/$dir"
  if [ -d "$dest/.git" ]; then
    echo "skip $dir (already cloned)"
    return
  fi
  echo "clone $dir"
  git clone --depth 1 --single-branch "$url" "$dest"
}

clone https://github.com/zhayinggang/ktv-home.git ktv-home
clone https://github.com/ShaoLongFei/home-ktv-system.git home-ktv-system
clone https://github.com/nomadkaraoke/python-audio-separator.git python-audio-separator
clone https://github.com/ijuinryukichi/lyric-align.git lyric-align
clone https://github.com/delete039/nicokara-studio.git nicokara-studio
clone https://github.com/rzru/nightingale.git nightingale
clone https://github.com/thedavidweng/OpenKara.git OpenKara
clone https://github.com/jingx8885/lovjpn.git lovjpn
clone https://github.com/joeseesun/qiaomu-mtv-creator.git qiaomu-mtv-creator

echo "vendor clones ready"
