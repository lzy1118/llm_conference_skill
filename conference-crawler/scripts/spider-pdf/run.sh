#!/bin/zsh
set -euo pipefail

# 所有支持会议共用的统一 shell 入口。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -lt 1 ]]; then
  print "用法: $0 <conference> [args...]"
  print "可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs"
  exit 1
fi

conference="$1"
shift

# The crawler project requires Python 3.13. Prefer its locked virtualenv so
# the system Python (which may be older) is never used accidentally.
DOWNLOAD_DIR="$SCRIPT_DIR/../download"
if [[ -x "$DOWNLOAD_DIR/.venv/bin/python" ]]; then
  export CRAWLER_PYTHON="$DOWNLOAD_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  export CRAWLER_PYTHON="uv run --project $DOWNLOAD_DIR python"
else
  export CRAWLER_PYTHON="python3"
fi

case "$conference" in
  asiacrypt|crypto|eurocrypt|ndss|usenix_security|ieee_s\&p|ccs)
    if [[ "$CRAWLER_PYTHON" == uv\ run\ * ]]; then
      uv run --project "$DOWNLOAD_DIR" python "$SCRIPT_DIR/spider.py" "$conference" "$@"
    else
      "$CRAWLER_PYTHON" "$SCRIPT_DIR/spider.py" "$conference" "$@"
    fi
    ;;
  *)
    print "不支持的 conference: $conference"
    print "可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs"
    exit 1
    ;;
esac
