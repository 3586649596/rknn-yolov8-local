import argparse
import os
import re
import shutil
import subprocess
import time

import cv2
import numpy as np

from yolov8 import CLASSES, COCO_test_helper, IMG_SIZE, post_process, setup_model


def open_camera(camera_id: str, width: int, height: int, fps: int):
    use_index = camera_id.isdigit()
    if use_index:
        cam_index = int(camera_id)
        cap = cv2.VideoCapture(cam_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
    else:
        cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        raise RuntimeError(f"Failed to open camera source: {camera_id}")
    return cap


def is_rkaiq_alive() -> bool:
    proc = subprocess.run(
        ["pgrep", "-x", "rkaiq_3A_server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


class FallbackAE:
    def __init__(self, subdev: str, target: float, interval: int):
        self.subdev = subdev
        self.target = target
        self.interval = max(1, interval)
        self.available = shutil.which("v4l2-ctl") is not None and os.path.exists(subdev)

        self.exp_min = 4
        self.exp_max = 2242
        self.gain_min = 0
        self.gain_max = 240
        self.exposure = 1200
        self.gain = 64

        if self.available:
            self._load_limits()
            self._load_current()

    def _run(self, args):
        return subprocess.run(
            ["v4l2-ctl", "-d", self.subdev] + args,
            capture_output=True,
            text=True,
            check=False,
        )

    def _load_limits(self):
        out = self._run(["-L"])
        if out.returncode != 0:
            self.available = False
            return

        m = re.search(r"exposure.*min=(\d+).*max=(\d+)", out.stdout)
        if m:
            self.exp_min, self.exp_max = int(m.group(1)), int(m.group(2))
        m = re.search(r"analogue_gain.*min=(\d+).*max=(\d+)", out.stdout)
        if m:
            self.gain_min, self.gain_max = int(m.group(1)), int(m.group(2))

    def _load_current(self):
        out = self._run(["--get-ctrl", "exposure,analogue_gain"])
        if out.returncode != 0:
            return
        m = re.search(r"exposure:\s*(\d+)", out.stdout)
        if m:
            self.exposure = int(m.group(1))
        m = re.search(r"analogue_gain:\s*(\d+)", out.stdout)
        if m:
            self.gain = int(m.group(1))

    def _apply(self):
        self.exposure = int(np.clip(self.exposure, self.exp_min, self.exp_max))
        self.gain = int(np.clip(self.gain, self.gain_min, self.gain_max))
        self._run(
            [
                "--set-ctrl",
                f"exposure={self.exposure},analogue_gain={self.gain}",
            ]
        )

    def update(self, luma: float, frame_idx: int):
        if not self.available or frame_idx % self.interval != 0:
            return

        low = self.target - 12.0
        high = self.target + 12.0

        if luma < low:
            scale = min(1.8, self.target / max(luma, 1.0))
            self.exposure += int(40 * scale)
            if self.exposure >= self.exp_max - 8:
                self.gain += int(6 * scale)
            self._apply()
        elif luma > high:
            scale = min(1.8, luma / max(self.target, 1.0))
            if self.gain > self.gain_min:
                self.gain -= int(6 * scale)
            else:
                self.exposure -= int(40 * scale)
            self._apply()


def enhance_low_light(
    frame: np.ndarray,
    target_luma: float,
    max_gain: float,
    clahe_clip: float,
    wb_strength: float,
):
    # Enhance luminance in LAB space for better color fidelity.
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)

    cur_luma = float(np.mean(l_chan))
    gain = target_luma / max(cur_luma, 1.0)
    gain = float(np.clip(gain, 1.0, max_gain))

    l_gain = np.clip(l_chan.astype(np.float32) * gain, 0.0, 255.0).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l_clahe = clahe.apply(l_gain)
    l_out = cv2.addWeighted(l_gain, 0.65, l_clahe, 0.35, 0.0)

    lab_out = cv2.merge([l_out, a_chan, b_chan])
    out = cv2.cvtColor(lab_out, cv2.COLOR_LAB2BGR)

    # Mild gray-world white balance to reduce color cast in low light.
    if wb_strength > 0.0:
        b, g, r = cv2.split(out.astype(np.float32))
        mb, mg, mr = float(np.mean(b)), float(np.mean(g)), float(np.mean(r))
        m_all = (mb + mg + mr) / 3.0
        sb = 1.0 + ((m_all / max(mb, 1e-6)) - 1.0) * wb_strength
        sg = 1.0 + ((m_all / max(mg, 1e-6)) - 1.0) * wb_strength
        sr = 1.0 + ((m_all / max(mr, 1e-6)) - 1.0) * wb_strength
        out = cv2.merge(
            [
                np.clip(b * sb, 0.0, 255.0),
                np.clip(g * sg, 0.0, 255.0),
                np.clip(r * sr, 0.0, 255.0),
            ]
        ).astype(np.uint8)

    return out, cur_luma, gain


def apply_saturation(frame: np.ndarray, sat_gain: float):
    if abs(sat_gain - 1.0) < 1e-6:
        return frame

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = np.clip(s.astype(np.float32) * sat_gain, 0.0, 255.0).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([h, s, v]), cv2.COLOR_HSV2BGR)


def preprocess_frame(frame: np.ndarray, platform: str, co_helper: COCO_test_helper):
    img = co_helper.letter_box(
        im=frame.copy(),
        new_shape=(IMG_SIZE[1], IMG_SIZE[0]),
        pad_color=(0, 0, 0),
    )
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    if platform in ["pytorch", "onnx"]:
        input_data = img.transpose((2, 0, 1))
        input_data = input_data.reshape(1, *input_data.shape).astype(np.float32)
        input_data = input_data / 255.0
    elif platform == "rknn":
        input_data = np.expand_dims(img, 0)
    else:
        input_data = img
    return input_data


def draw_detections(image: np.ndarray, boxes, scores, classes):
    for box, score, cl in zip(boxes, scores, classes):
        x1, y1, x2, y2 = [int(v) for v in box]
        label = f"{CLASSES[cl].strip()} {score:.2f}"
        cv2.rectangle(image, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(
            image,
            label,
            (x1, max(y1 - 8, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )


def ensure_video_writer(path: str, fps: int, width: int, height: int):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, float(fps), (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer: {path}")
    return writer


def parse_args():
    parser = argparse.ArgumentParser(
        description="YOLOv8 RKNN realtime camera inference"
    )
    parser.add_argument(
        "--model_path",
        type=str,
        default="../model/yolov8.rknn",
        help="Path to .rknn/.onnx/.pt model",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="rk3588",
        help="Target platform for RKNN runtime",
    )
    parser.add_argument("--device_id", type=str, default=None, help="Device id")
    parser.add_argument(
        "--camera_id",
        type=str,
        default="0",
        help="Camera index like 0/1, or stream URL",
    )
    parser.add_argument("--width", type=int, default=1280, help="Capture width")
    parser.add_argument("--height", type=int, default=720, help="Capture height")
    parser.add_argument("--fps", type=int, default=30, help="Capture/record fps")
    parser.add_argument(
        "--sensor_subdev",
        type=str,
        default="/dev/v4l-subdev2",
        help="Sensor subdev for fallback AE (when rkaiq is down)",
    )
    parser.add_argument(
        "--ae_target",
        type=float,
        default=95.0,
        help="Target luma for fallback sensor AE",
    )
    parser.add_argument(
        "--ae_interval",
        type=int,
        default=8,
        help="Fallback AE update interval (frames)",
    )
    parser.add_argument(
        "--disable_fallback_ae",
        action="store_true",
        help="Disable fallback sensor AE adjustment",
    )
    parser.add_argument(
        "--target_luma",
        type=float,
        default=130.0,
        help="Target brightness for low-light enhancement",
    )
    parser.add_argument(
        "--max_gain",
        type=float,
        default=2.4,
        help="Max brightness gain for low-light enhancement",
    )
    parser.add_argument(
        "--clahe_clip",
        type=float,
        default=2.2,
        help="CLAHE clip limit for low-light enhancement",
    )
    parser.add_argument(
        "--wb_strength",
        type=float,
        default=0.35,
        help="White-balance correction strength, 0~1",
    )
    parser.add_argument(
        "--disable_enhance",
        action="store_true",
        help="Disable low-light enhancement",
    )
    parser.add_argument(
        "--sat_gain",
        type=float,
        default=1.0,
        help="Saturation gain, 1.0 keeps original color",
    )
    parser.add_argument(
        "--swap_rb",
        action="store_true",
        help="Swap red/blue channels for cameras with wrong color order",
    )
    parser.add_argument(
        "--save_video",
        type=str,
        default="",
        help="Optional output video path, e.g. ./result/camera.mp4",
    )
    parser.add_argument(
        "--max_frames",
        type=int,
        default=0,
        help="Stop after N frames, 0 means run forever",
    )
    parser.add_argument(
        "--no_window",
        action="store_true",
        help="Disable preview window for headless mode",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    model, platform = setup_model(args)
    cap = open_camera(args.camera_id, args.width, args.height, args.fps)
    co_helper = COCO_test_helper(enable_letter_box=True)
    writer = None
    render_needed = (not args.no_window) or bool(args.save_video)
    rkaiq_ok = is_rkaiq_alive()
    fallback_ae = None
    # Fallback AE is temporarily disabled by request.
    # if (not rkaiq_ok) and (not args.disable_fallback_ae):
    #     fallback_ae = FallbackAE(
    #         subdev=args.sensor_subdev,
    #         target=args.ae_target,
    #         interval=args.ae_interval,
    #     )

    fps_ema = 0.0
    t_prev = time.time()
    frame_idx = 0

    try:
        print(
            f"Camera source: {args.camera_id}, no_window={args.no_window}",
            flush=True,
        )
        print(f"rkaiq alive: {rkaiq_ok}", flush=True)
        # if fallback_ae is not None:
        #     print(
        #         f"fallback AE enabled on {fallback_ae.subdev} "
        #         f"(exp={fallback_ae.exposure}, gain={fallback_ae.gain})",
        #         flush=True,
        #     )
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to read frame from camera, exit.", flush=True)
                break

            if args.swap_rb:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            luma = float(np.mean(frame))
            # if fallback_ae is not None:
            #     fallback_ae.update(luma=luma, frame_idx=frame_idx)
            gain = 1.0
            if not args.disable_enhance:
                frame, luma, gain = enhance_low_light(
                    frame,
                    target_luma=args.target_luma,
                    max_gain=args.max_gain,
                    clahe_clip=args.clahe_clip,
                    wb_strength=args.wb_strength,
                )

            input_data = preprocess_frame(frame, platform, co_helper)
            outputs = model.run([input_data])
            boxes, classes, scores = post_process(outputs)

            det_count = 0
            if classes is not None:
                det_count = len(classes)

            vis = None
            if render_needed:
                vis = frame.copy()
                vis = apply_saturation(vis, args.sat_gain)
            if boxes is not None and render_needed:
                real_boxes = co_helper.get_real_box(boxes)
                draw_detections(vis, real_boxes, scores, classes)

            t_now = time.time()
            inst_fps = 1.0 / max(t_now - t_prev, 1e-6)
            fps_ema = inst_fps if fps_ema == 0.0 else 0.9 * fps_ema + 0.1 * inst_fps
            t_prev = t_now

            if render_needed:
                cv2.putText(
                    vis,
                    f"FPS: {fps_ema:.2f}  DET: {det_count}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                )
                cv2.putText(
                    vis,
                    f"LUMA: {luma:.1f}  GAIN: {gain:.2f}",
                    (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 255),
                    2,
                )

            if args.save_video:
                if writer is None:
                    writer = ensure_video_writer(
                        args.save_video, args.fps, vis.shape[1], vis.shape[0]
                    )
                writer.write(vis)

            if args.no_window:
                if frame_idx % 60 == 0:
                    print(
                        f"frame={frame_idx}, fps={fps_ema:.2f}, det={det_count}, "
                        f"luma={luma:.1f}, gain={gain:.2f}",
                        flush=True,
                    )
            else:
                cv2.imshow("YOLOv8 Camera", vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    break

            frame_idx += 1
            if args.max_frames > 0 and frame_idx >= args.max_frames:
                break
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if not args.no_window:
            cv2.destroyAllWindows()
        if hasattr(model, "rknn") and hasattr(model.rknn, "release"):
            model.rknn.release()


if __name__ == "__main__":
    main()
