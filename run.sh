#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${WORKMATE_HOST:-127.0.0.1}"
PORT="${WORKMATE_PORT:-7860}"
URL="http://${HOST}:${PORT}"

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  echo "已创建 .env。请先打开 .env 填写 LLM_API_KEY，然后重新运行 ./run.sh。"
  exit 1
fi

if ! grep -Eq '^LLM_API_KEY=.+$' ".env" || grep -Eq '^LLM_API_KEY=(your-api-key-here|)$' ".env"; then
  echo "请先在 .env 中填写有效的 LLM_API_KEY，然后重新运行 ./run.sh。"
  exit 1
fi

if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx "agent"; then
  PYTHON_CMD=(conda run -n agent python)
else
  if [ ! -d ".venv" ]; then
    echo "未检测到 conda agent 环境，正在创建本地 .venv..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  PYTHON_CMD=(python)
fi

echo "正在安装/检查依赖..."
"${PYTHON_CMD[@]}" -m pip install -r requirements.txt

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

echo "Workmate Agent 正在启动：${URL}"
echo "保持这个终端窗口运行即可。需要停止时按 Ctrl+C。"
exec "${PYTHON_CMD[@]}" -m src.web
