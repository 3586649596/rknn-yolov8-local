#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/radxa/Desktop/rknn_yolov8_test"
EXAMPLE_DIR="${ROOT}/code/rknn_model_zoo/examples/yolov8/python"
MODEL_PATH="${1:-${ROOT}/model/yolov8.rknn}"
CAMERA_ID="${2:-0}"

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

/home/radxa/miniconda3/bin/conda run -n rknn-yolo python \
  "${EXAMPLE_DIR}/yolov8_camera.py" \
  --model_path "${MODEL_PATH}" \
  --target rk3588 \
  --camera_id "${CAMERA_ID}" \
  "${@:3}"
