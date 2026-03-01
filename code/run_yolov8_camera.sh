#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/radxa/Desktop/rknn_yolov8_test"
EXAMPLE_DIR="${ROOT}/code/rknn_model_zoo/examples/yolov8/python"
MODEL_PATH="${1:-${ROOT}/model/yolov8.rknn}"
CAMERA_ID="${2:-0}"
RKAIQ_PID_FILE="/tmp/rknn_yolov8_rkaiq_workaround.pid"
RKAIQ_LOG_FILE="${ROOT}/logs/rkaiq_workaround.log"
RKAIQ_STARTED_BY_SCRIPT=0

is_rkaiq_running() {
  pgrep -x rkaiq_3A_server >/dev/null 2>&1
}

start_rkaiq_workaround() {
  if is_rkaiq_running; then
    echo "[rkaiq] already running"
    return 0
  fi

  echo "[rkaiq] not running, starting workaround..."
  # Run rkaiq in a private mount namespace and hide /dev/media3
  # to avoid the known crash path on this board image.
  unshare -Urnm bash -lc '
    mount --bind /dev/null /dev/media3
    exec /usr/bin/rkaiq_3A_server --silent
  ' >>"${RKAIQ_LOG_FILE}" 2>&1 &
  echo "$!" >"${RKAIQ_PID_FILE}"
  sleep 1

  if is_rkaiq_running; then
    RKAIQ_STARTED_BY_SCRIPT=1
    echo "[rkaiq] workaround started"
    return 0
  fi

  echo "[rkaiq] workaround failed to start, continue with fallback AE in python"
  return 1
}

stop_rkaiq_workaround_if_needed() {
  local pid
  if [[ "${RKAIQ_STARTED_BY_SCRIPT}" != "1" ]]; then
    return 0
  fi
  if [[ -f "${RKAIQ_PID_FILE}" ]]; then
    pid="$(cat "${RKAIQ_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      sleep 0.2
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${RKAIQ_PID_FILE}"
  fi
  echo "[rkaiq] workaround stopped"
}

trap stop_rkaiq_workaround_if_needed EXIT INT TERM

# Accept project root path and auto-resolve model file.
if [[ -d "${MODEL_PATH}" ]]; then
  if [[ -f "${MODEL_PATH}/model/yolov8.rknn" ]]; then
    MODEL_PATH="${MODEL_PATH}/model/yolov8.rknn"
  elif [[ -f "${MODEL_PATH}/yolov8.rknn" ]]; then
    MODEL_PATH="${MODEL_PATH}/yolov8.rknn"
  else
    echo "Error: no model file found under directory: ${MODEL_PATH}" >&2
    echo "Expected one of:" >&2
    echo "  ${MODEL_PATH}/model/yolov8.rknn" >&2
    echo "  ${MODEL_PATH}/yolov8.rknn" >&2
    exit 1
  fi
fi

if [[ ! -f "${MODEL_PATH}" ]]; then
  echo "Error: model file not found: ${MODEL_PATH}" >&2
  exit 1
fi

export PYTHONPATH="/usr/lib/python3/dist-packages"
mkdir -p "${ROOT}/logs"

# Set RKAIQ_AUTO_WORKAROUND=0 to disable this behavior.
if [[ "${RKAIQ_AUTO_WORKAROUND:-1}" == "1" ]]; then
  start_rkaiq_workaround || true
fi

/home/radxa/miniconda3/bin/conda run -n rknn-yolo python \
  "${EXAMPLE_DIR}/yolov8_camera.py" \
  --model_path "${MODEL_PATH}" \
  --target rk3588 \
  --camera_id "${CAMERA_ID}" \
  "${@:3}"
