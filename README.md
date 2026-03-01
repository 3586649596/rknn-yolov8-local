# RK3588 YOLOv8 板端推理文档

验证日期：2026-02-28  
验证平台：Radxa ROCK 5B Plus（RK3588）/ Debian 12（Radxa OS）

## 1. 目录说明

```text
/home/radxa/Desktop/rknn_yolov8_test
├── code
│   ├── run_yolov8.sh                 # 单图推理一键脚本
│   ├── run_yolov8_camera.sh          # 摄像头实时推理一键脚本
│   └── rknn_model_zoo/.../python
│       ├── yolov8.py                 # 官方示例（已做 numpy DFL 兼容）
│       └── yolov8_camera.py          # 新增实时摄像头脚本
├── model
│   ├── yolov8.rknn                   # 预转换 RK3588 模型
│   └── bus.jpg                       # 测试图片
├── result                            # 输出结果目录
└── logs
```

## 2. 环境说明

- Conda：`/home/radxa/miniconda3`
- 环境名：`rknn-yolo`
- 关键依赖：`numpy`、`opencv`、系统 `rknnlite`
- 运行脚本时已自动设置：
  - `PYTHONPATH=/usr/lib/python3/dist-packages`
  - 使用 `conda run -n rknn-yolo`

## 3. 单图推理

### 3.1 一键运行

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8.sh
```

### 3.2 指定模型运行

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8.sh /home/radxa/Desktop/rknn_yolov8_test/model/yolov8.rknn
```

### 3.3 结果位置

- 示例脚本原始输出：`code/rknn_model_zoo/examples/yolov8/python/result/bus.jpg`
- 已自动同步到：`/home/radxa/Desktop/rknn_yolov8_test/result/bus.jpg`

## 4. 摄像头实时推理

### 4.1 最常用命令

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22
```

说明：
- 第 1 个参数可以传模型文件，也可以直接传工程目录（脚本会自动解析到 `model/yolov8.rknn`）。
- 第 2 个参数是摄像头 ID。

### 4.2 无窗口模式（SSH/CLI 推荐）

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window --max_frames 300
```

### 4.3 保存检测视频

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --save_video /home/radxa/Desktop/rknn_yolov8_test/result/camera.mp4
```

### 4.4 自定义分辨率和帧率

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --width 1280 --height 720 --fps 30
```

### 4.5 rkaiq 异常时自动兜底

当前脚本已内置：
- `rkaiq` 存活检测（日志会打印 `rkaiq alive: False/True`）
- 当 `rkaiq` 不在运行时，自动启用传感器 fallback AE（通过 `v4l2-ctl` 调整 `exposure/analogue_gain`）

常用参数：

```bash
# 指定传感器子设备并调 AE 目标亮度
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --sensor_subdev /dev/v4l-subdev2 --ae_target 95 --ae_interval 8
```

```bash
# 若你手动确认 rkaiq 已恢复，可关闭 fallback AE
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --disable_fallback_ae
```

## 5. 摄像头排查

### 5.1 列出视频设备

```bash
ls -l /dev/video*
```

当前机器可见 `video-camera0 -> video22`，一般可优先尝试 `22`。

### 5.2 快速测试某个 camera_id 是否能读帧

```bash
PYTHONPATH=/usr/lib/python3/dist-packages /home/radxa/miniconda3/bin/conda run -n rknn-yolo python -c "import cv2; cap=cv2.VideoCapture(22, cv2.CAP_V4L2); print('opened', cap.isOpened()); ret,frame=cap.read(); print('ret', ret, 'shape', None if frame is None else frame.shape); cap.release()"
```

## 6. 常见问题

### 6.1 报错：`... is not rknn/pytorch/onnx model`

原因：`--model_path` 传成了目录，或命令被换行拆开导致参数断裂。  
建议：整行输入命令，不要在路径中间换行。

正确示例：

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22
```

### 6.2 报错：`bash: model/yolov8.rknn: No such file or directory`

原因：上一行命令已结束，下一行 `model/yolov8.rknn` 被当成新命令执行。  
处理：把参数放在同一行。

### 6.3 警告：`Query dynamic range failed ... static shape`

这是静态 shape RKNN 模型常见提示，可忽略，不影响当前推理。

### 6.4 结论：`rkaiq` 当前是崩溃退出，不是简单未启动

本机实测 `rkaiq_3A_server` 会在初始化阶段 `SIGSEGV`（退出码 139），
回溯位于 `librkaiq.so` 的 `rk_aiq_uapi_sysctl_init`。因此 `systemctl` 显示 inactive。

可复现命令：

```bash
/usr/bin/rkaiq_3A_server --silent; echo $?
# 预期可见 139（Segmentation fault）
```

在官方修复前，建议使用当前脚本的 fallback AE + 软件白平衡/增亮路径。

## 7. 脚本入口

- 单图：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8.sh`
- 摄像头：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh`
