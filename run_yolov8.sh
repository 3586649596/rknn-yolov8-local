#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/radxa/Desktop/rknn_yolov8_test"
EXAMPLE_DIR="${ROOT}/code/rknn_model_zoo/examples/yolov8/python"
MODEL_PATH="${1:-${ROOT}/model/yolov8.rknn}"

export PYTHONPATH="/usr/lib/python3/dist-packages"

/home/radxa/miniconda3/bin/conda run -n rknn-yolo python \
  "${EXAMPLE_DIR}/yolov8.py" \
  --model_path "${MODEL_PATH}" \
  --target rk3588 \
  --img_folder "${ROOT}/model" \
  --img_save

cp -f "${EXAMPLE_DIR}/result/bus.jpg" "${ROOT}/result/bus.jpg"

echo "Result image: ${EXAMPLE_DIR}/result/bus.jpg"
