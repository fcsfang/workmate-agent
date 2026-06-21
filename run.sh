#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${WORKMATE_HOST:-127.0.0.1}"
PORT="${WORKMATE_PORT:-7860}"
URL="http://${HOST}:${PORT}"
DOCS_URL="${URL}/docs"

say() {
  printf '%s\n' "$1"
}

fail() {
  printf '启动失败：%s\n' "$1" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

port_in_use() {
  if command_exists lsof; then
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  python3 - <<PY >/dev/null 2>&1
import socket
sock = socket.socket()
try:
    sock.bind(("${HOST}", int("${PORT}")))
except OSError:
    raise SystemExit(0)
finally:
    sock.close()
raise SystemExit(1)
PY
}

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  say "已创建 .env。请先打开 .env 填写 LLM_API_KEY，然后重新运行 ./run.sh。"
  exit 1
fi

if ! grep -Eq '^LLM_API_KEY=.+$' ".env" || grep -Eq '^LLM_API_KEY=(your-api-key-here|)$' ".env"; then
  say "请先在 .env 中填写有效的 LLM_API_KEY，然后重新运行 ./run.sh。"
  exit 1
fi

if [ ! -f "requirements.txt" ]; then
  fail "未找到 requirements.txt，请确认当前目录是 Workmate Agent 项目根目录。"
fi

if port_in_use; then
  fail "端口 ${PORT} 已被占用。请先关闭占用进程，或使用 WORKMATE_PORT=7861 ./run.sh 指定其它端口。"
fi

if command_exists conda && conda env list | awk '{print $1}' | grep -qx "agent"; then
  PYTHON_CMD=(conda run -n agent python)
else
  if [ ! -d ".venv" ]; then
    command_exists python3 || fail "未检测到 python3。请先安装 Python 3.12+，或创建 conda agent 环境。"
    say "未检测到 conda agent 环境，正在创建本地 .venv..."
    python3 -m venv .venv || fail "创建 .venv 失败，请检查 Python/venv 是否可用。"
  fi
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  PYTHON_CMD=(python)
fi

say "正在安装/检查依赖..."
"${PYTHON_CMD[@]}" -m pip install -r requirements.txt || fail "依赖安装失败。请检查网络、pip 源或 requirements.txt。"

(
  "${PYTHON_CMD[@]}" - <<PY
import time
import urllib.request
import webbrowser

url = "${URL}"
for _ in range(60):
    try:
        urllib.request.urlopen(url, timeout=1).close()
        webbrowser.open(url)
        break
    except Exception:
        time.sleep(0.5)
PY
) >/dev/null 2>&1 &

say "Workmate Agent 正在启动：${URL}"
say "OpenAPI 文档：${DOCS_URL}"
say "保持这个终端窗口运行即可。需要停止时按 Ctrl+C。"
exec "${PYTHON_CMD[@]}" -m src.web
