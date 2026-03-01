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

### 4.4.1 提升画面饱和度

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --sat_gain 1.2
```

### 4.4.2 切换 NPU 核心掩码

默认使用三核：

```bash
RKNN_NPU_CORE_MASK=0_1_2 /home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window
```

单核对比：

```bash
RKNN_NPU_CORE_MASK=0 /home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window
```

### 4.5 rkaiq 异常时自动兜底

当前脚本已内置：
- `rkaiq` 自动 workaround（默认开启）：当 `rkaiq_3A_server` 未运行时，`run_yolov8_camera.sh` 会在私有 namespace 中屏蔽 `/dev/media3` 并拉起 `rkaiq`，退出脚本后自动回收。
- `rkaiq` 存活检测（日志会打印 `rkaiq alive: False/True`）
- 说明：当前版本里 Python fallback AE 已按排查需求注释停用（只走 `rkaiq` 路径）

可选：如需关闭自动 workaround，可在命令前加：

```bash
RKAIQ_AUTO_WORKAROUND=0 /home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window --max_frames 300
```

说明：
- `--sensor_subdev / --ae_target / --ae_interval / --disable_fallback_ae` 参数当前保留但未生效（fallback AE 代码已注释停用）。

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

在官方修复前，建议使用当前脚本的 `rkaiq` workaround 路径；如需调观感，可使用 `--sat_gain` 和（可选）低光增强参数。

## 7. 脚本入口

- 单图：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8.sh`
- 摄像头：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh`
