#!/bin/bash
cd "$(dirname "$0")" || exit 1
for py in .venv/bin/python ../InsightFlow-AI-V2/.venv/bin/python; do
  if [ -x "$py" ]; then exec "$py" launch.py --open; fi
done
printf '请按 README 安装 Python 环境后启动演示。\n'
exit 1
