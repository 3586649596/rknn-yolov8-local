# RKAIQ 排障记录（2026-03-01）

## 1. 问题背景
用户反馈 MIPI 摄像头“有画面但不正常”，怀疑与 `rkaiq` 相关。目标是确认根因并给出可落地修复，保证 YOLOv8 摄像头测试脚本可稳定使用。

## 2. 环境信息
- 板卡：ROCK 5B Plus（RK3588）
- 系统：Debian 12（Radxa 镜像）
- 内核：`6.1.84-8-rk2410`
- 关键包：`camera-engine-rkaiq 6.8.0-rk3588`
- 关键包：`rockchip-iqfiles-rk3588 0.2.6`
- 关键包：`linux-image-6.1.84-8-rk2410 6.1.84-8`
- 传感器：`imx415`（`/dev/v4l-subdev2`）

## 3. 初始现象
- `rkaiq_3A.service` 处于 `inactive (dead)`。
- 手动运行 `/usr/bin/rkaiq_3A_server` 会崩溃，退出码 `139`（Segmentation fault）。
- 摄像头链路存在，但自动曝光表现异常。

## 4. 排查过程（时间线）
1. 检查安装和服务状态，确认不是“未安装”问题。

```bash
dpkg -l | grep -i camera-engine-rkaiq
systemctl status rkaiq_3A.service
```

2. 前台直跑 `rkaiq` 复现崩溃，确认是进程级问题。

```bash
/usr/bin/rkaiq_3A_server
echo $?
```

3. 检查 media 拓扑，确认主相机链路和 ISP 连接关系。

```bash
v4l2-ctl --list-devices
media-ctl -p -d /dev/media0
media-ctl -p -d /dev/media2
media-ctl -p -d /dev/media3
```

4. 分别做抓流验证，确认“链路是否通”。

```bash
v4l2-ctl -d /dev/video0  --stream-mmap=4 --stream-count=60  --stream-to=/tmp/v0.raw
v4l2-ctl -d /dev/video22 --stream-mmap=4 --stream-count=120 --stream-to=/tmp/v22.yuv
v4l2-ctl -d /dev/video31 --stream-mmap=4 --stream-count=120 --stream-to=/tmp/v31.nv12
```

5. 读取传感器控制量，确认 `rkaiq` 异常时 AE 参数不更新。

```bash
v4l2-ctl -d /dev/v4l-subdev2 --get-ctrl=exposure,analogue_gain
```

## 5. 关键结论
- MIPI 主链路不是“完全断链”，`/dev/video0` 和 `/dev/video22` 都能稳定出流。
- 问题核心是 `rkaiq_3A_server` 在当前媒体拓扑下崩溃（`exit 139`）。
- `/dev/media3` 对应 `rkisp1` 路径（不是 MIPI DSI 显示接口），当前场景无有效输入，和崩溃路径高度相关。
- `rkaiq` 崩溃后，自动曝光/白平衡等 3A 能力无法稳定工作，导致“画面不正常”。

## 6. 临时修复方案（已验证）
- 在私有 mount namespace 内启动 `rkaiq`。
- 在该 namespace 内将 `/dev/media3` 绑定到 `/dev/null`，避开崩溃路径。
- 结果：`rkaiq_3A_server` 可稳定存活，`/dev/video22` 可持续抓流，自动曝光恢复可用。

示例核心命令：

```bash
unshare -Urnm bash -lc 'mount --bind /dev/null /dev/media3; exec /usr/bin/rkaiq_3A_server --silent'
```

## 7. 已合并到项目脚本
- 修改文件：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh`
- 行为变更：
1. 启动推理前自动检查 `rkaiq_3A_server`。
2. 若未运行，自动拉起上述 workaround。
3. 脚本退出时，自动回收本次拉起的 workaround 进程。
4. 支持 `RKAIQ_AUTO_WORKAROUND=0` 关闭自动行为。

- 文档同步：`/home/radxa/Desktop/rknn_yolov8_test/README.md` 第 4.5 节已更新。

## 8. 当前使用方式
默认（建议）：

```bash
/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window --max_frames 300
```

关闭 workaround（用于对比或后续官方修复验证）：

```bash
RKAIQ_AUTO_WORKAROUND=0 /home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh /home/radxa/Desktop/rknn_yolov8_test 22 --no_window --max_frames 300
```

## 9. 现状与风险
- 现状：脚本已可自动兜底处理 `rkaiq` 崩溃场景，实测日志包含 `rkaiq alive: True`。
- 风险：这是临时规避，不是 `camera-engine-rkaiq` 根因修复。
- 风险：若未来要启用第二路相机（`rkisp1`），需重新评估该 workaround。

## 10. 后续建议
1. 向 Radxa 提交问题，附上版本和 `exit 139` 复现信息。
2. 跟进官方包更新后，关闭 workaround 再做回归。
3. 若后续启用双目/双路摄像头，重新设计 `rkaiq` 启动策略。

## 11. 相关文件
- 启动脚本：`/home/radxa/Desktop/rknn_yolov8_test/code/run_yolov8_camera.sh`
- 项目说明：`/home/radxa/Desktop/rknn_yolov8_test/README.md`
- 运行日志：`/home/radxa/Desktop/rknn_yolov8_test/logs/rkaiq_workaround.log`
