#!/usr/bin/env python3
# =============================================================================
# Segmentation Node — loads a TorchScript DeepLabV3 model and runs inference
# on incoming camera images.
#
# Subscribes : /camera/image_raw   (sensor_msgs/Image)
# Publishes  : /perception/segmentation (sensor_msgs/Image)  — colored mask
# =============================================================================

import csv
import os
import signal
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

import torch
import cv2


class SegmentationNode(Node):
    def __init__(self):
        super().__init__('segmentation_node')

        # ── Parameters ──────────────────────────────────────────────────────
        self.declare_parameter('model_path', 'segmentation_model_camvid.pt')
        self.declare_parameter('class_dict_path', 'label_colors.csv')
        self.declare_parameter('output_path', '/data/output/comparison.mp4')
        self.declare_parameter('output_fps', 10.0)
        self.declare_parameter('write_video', True)

        model_path = self.get_parameter('model_path').get_parameter_value().string_value
        class_dict_path = self.get_parameter('class_dict_path').get_parameter_value().string_value
        self.output_path = self.get_parameter('output_path').get_parameter_value().string_value
        self.output_fps = float(self.get_parameter('output_fps').get_parameter_value().double_value)
        self.write_video = bool(self.get_parameter('write_video').get_parameter_value().bool_value)

        # ── Load class colors from label_colors.csv (Carla)
        self.class_colors, self.class_names = self._load_class_colors(class_dict_path)
        self.num_classes = len(self.class_colors)
        self.get_logger().info(f'Loaded {self.num_classes} classes from {class_dict_path}')

        # Ensure output directory exists (when writing video)
        if self.write_video:
            out_dir = os.path.dirname(self.output_path)
            if out_dir and not os.path.isdir(out_dir):
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except Exception as e:
                    self.get_logger().warn(f'Could not create output directory {out_dir}: {e}')

        # ── Build color lookup table (index → BGR) for fast mapping
        # Shape: (num_classes, 3) in BGR order for OpenCV
        self.color_lut = np.zeros((self.num_classes, 3), dtype=np.uint8)
        for idx, (r, g, b) in enumerate(self.class_colors):
            self.color_lut[idx] = [b, g, r]  # OpenCV uses BGR

        # Build color code -> index map for GT color mapping (code = r<<16|g<<8|b)
        self.color_to_idx = {}
        for idx, (r, g, b) in enumerate(self.class_colors):
            code = (int(r) << 16) | (int(g) << 8) | int(b)
            self.color_to_idx[code] = idx

        # Preferred drivable class names (will match names from CSV)
        preferred_drivable = ["Road", "RoadLine", "LaneMkgsDriv", "RoadShoulder"]
        self.drivable_indices = [i for i, n in enumerate(self.class_names) if n in preferred_drivable]
        if not self.drivable_indices:
            # fallback indices (CamVid defaults) if names not found
            # try to guess: Road commonly at index for color (128,64,128)
            for i, (r, g, b) in enumerate(self.class_colors):
                if (r, g, b) == (128, 64, 128):
                    self.drivable_indices.append(i)

        # ── Load TorchScript model ──────────────────────────────────────────
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.get_logger().info(f'Using device: {self.device}')

        self.model = torch.jit.load(model_path, map_location=self.device)
        self.model.eval()
        self.get_logger().info(f'Loaded TorchScript model: {model_path}')

        # ── ImageNet normalization constants (must match training) ──────────
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        self.input_h = 360
        self.input_w = 480

        # ── ROS2 bridge, subscriber, publisher ──────────────────────────────
        self.bridge = CvBridge()

        self.subscription = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 100)

        # Optional GT subscription published by the video camera node
        self.gt_frame = None
        self.gt_subscription = self.create_subscription(
            Image, '/camera/gt_image_raw', self.gt_callback, 10)

        self.publisher = self.create_publisher(
            Image, '/perception/segmentation', 10)

        # ── Video writer for saving comparison (camera | drivable | pred | gt)
        self.video_writer = None
        self.output_path = '/data/output/comparison.mp4'

        self.get_logger().info('Segmentation node ready — waiting for images...')

    # ── Load label_colors.csv / class mapping ─────────────────────────────────
    def _load_class_colors(self, csv_path):
        """Read a CSV of label colors (expects columns id,name,r,g,b).
        Returns (colors_list, names_list).

        If the CSV is missing or malformed, fall back to a small default palette
        so the node can still run.
        """
        colors = []
        names = []

        if not os.path.exists(csv_path):
            self.get_logger().warn(f"Class colors file not found: {csv_path}. Using fallback colors.")
            # Minimal fallback: Unlabeled + Road
            colors = [(0, 0, 0), (128, 64, 128)]
            names = ['Unlabeled', 'Road']
            return colors, names

        try:
            with open(csv_path, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Support files with or without 'name' column
                    name = row.get('name') or row.get('label') or ''
                    try:
                        r = int(row['r'].strip())
                        g = int(row['g'].strip())
                        b = int(row['b'].strip())
                    except Exception:
                        continue
                    colors.append((r, g, b))
                    names.append(name.strip())
        except Exception as e:
            self.get_logger().warn(f"Failed to read class colors from {csv_path}: {e}. Using fallback colors.")
            colors = [(0, 0, 0), (128, 64, 128)]
            names = ['Unlabeled', 'Road']

        if not colors:
            # Ensure we have at least one class
            colors = [(0, 0, 0)]
            names = ['Unlabeled']

        return colors, names

    def gt_callback(self, msg):
        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception:
            try:
                mono = self.bridge.imgmsg_to_cv2(msg, desired_encoding='mono8')
                bgr = cv2.cvtColor(mono, cv2.COLOR_GRAY2BGR)
            except Exception:
                return
        self.gt_frame = bgr

    def _prepare_gt_color(self, gt_bgr):
        # returns a colorized GT BGR image sized (input_h, input_w, 3)
        if gt_bgr is None:
            return np.zeros((self.input_h, self.input_w, 3), dtype=np.uint8)

        # Handle single-channel masks
        if gt_bgr.ndim == 2 or (gt_bgr.ndim == 3 and gt_bgr.shape[2] == 1):
            if gt_bgr.ndim == 3:
                gt_idx = gt_bgr[:, :, 0]
            else:
                gt_idx = gt_bgr
            gt_idx_resized = cv2.resize(gt_idx, (self.input_w, self.input_h), interpolation=cv2.INTER_NEAREST)
            return self.color_lut[gt_idx_resized]

        # Otherwise color-coded BGR mask
        gt_resized = cv2.resize(gt_bgr[:, :, :3], (self.input_w, self.input_h), interpolation=cv2.INTER_NEAREST)
        # compute packed codes (r<<16 | g<<8 | b)
        r = gt_resized[:, :, 2].astype(np.uint32)
        g = gt_resized[:, :, 1].astype(np.uint32)
        b = gt_resized[:, :, 0].astype(np.uint32)
        codes = (r << 16) | (g << 8) | b
        unique = np.unique(codes)
        idx_map = np.zeros_like(codes, dtype=np.uint8)
        for code in unique:
            idx = self.color_to_idx.get(int(code), 0)
            idx_map[codes == code] = idx
        return self.color_lut[idx_map]

    # ── Preprocess frame exactly like training ──────────────────────────────
    def _preprocess(self, bgr_frame):
        """Resize, convert to RGB, normalize, return tensor on device."""
        # Resize to model input size
        resized = cv2.resize(bgr_frame, (self.input_w, self.input_h),
                             interpolation=cv2.INTER_LINEAR)

        # BGR → RGB, uint8 → float32 [0, 1]
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

        # ImageNet normalization
        rgb = (rgb - self.mean) / self.std

        # HWC → CHW → NCHW
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
        return tensor.to(self.device)

    # ── Map class indices to a colored BGR image ────────────────────────────
    def _colorize_mask(self, class_map):
        """Convert a 2-D numpy class index array to a BGR color image."""
        return self.color_lut[class_map]  # fancy indexing → (H, W, 3) BGR

    # ── Image callback ──────────────────────────────────────────────────────
    def image_callback(self, msg):
        # Convert ROS Image → OpenCV BGR
        bgr_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

        # Preprocess
        input_tensor = self._preprocess(bgr_frame)

        # Run inference (no gradients needed)
        with torch.no_grad():
            output = self.model(input_tensor)['out']       # (1, C, H, W)
            pred = output.argmax(dim=1).squeeze(0)         # (H, W)
            class_map = pred.cpu().numpy().astype(np.uint8)

        # Colorize the segmentation mask (at model resolution)
        colored_mask = self._colorize_mask(class_map)

        # Build drivable mask (white where predicted class is drivable)
        drivable_mask_bin = np.isin(class_map, self.drivable_indices).astype(np.uint8) * 255
        drivable_bgr = np.stack([drivable_mask_bin, drivable_mask_bin, drivable_mask_bin], axis=2)

        # Prepare GT color panel from last GT frame (if available)
        gt_color = self._prepare_gt_color(self.gt_frame)

        # Resize camera to model input for consistent panels
        resized_cam = cv2.resize(bgr_frame, (self.input_w, self.input_h))

        # Compose 4-panel: camera | drivable (white=road) | prediction | GT
        composite = np.hstack([resized_cam, drivable_bgr, colored_mask, gt_color])

        # ── Write composite frame to video file (optional) ───────────────
        if self.write_video:
            if self.video_writer is None:
                h, w = composite.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                self.video_writer = cv2.VideoWriter(self.output_path, fourcc,
                                                    float(self.output_fps), (w, h))
                self.get_logger().info(f'Saving comparison video to {self.output_path} (@{self.output_fps} FPS)')
            if self.video_writer.isOpened():
                self.video_writer.write(composite)
            else:
                self.get_logger().warn(f'VideoWriter failed to open: {self.output_path}')

        # Resize prediction to original frame size for downstream publish
        h_orig, w_orig = bgr_frame.shape[:2]
        colored_mask_full = cv2.resize(colored_mask, (w_orig, h_orig), interpolation=cv2.INTER_NEAREST)

        # Publish predicted colored segmentation as before
        out_msg = self.bridge.cv2_to_imgmsg(colored_mask_full, encoding='bgr8')
        out_msg.header = msg.header
        self.publisher.publish(out_msg)


# ── Main ────────────────────────────────────────────────────────────────────
def main(args=None):
    rclpy.init(args=args)
    node = SegmentationNode()

    # Ensure video writer is released even on SIGTERM/SIGKILL
    def _shutdown_handler(signum, frame):
        if node.video_writer is not None:
            node.video_writer.release()
            node.get_logger().info('Segmentation video saved.')
        node.destroy_node()
        rclpy.try_shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if node.video_writer is not None:
            node.video_writer.release()
            node.get_logger().info('Segmentation video saved.')
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
