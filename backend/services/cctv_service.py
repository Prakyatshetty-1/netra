"""CCTV Video Ingestion, OpenCV Frame Sampling & YOLO Object Detection Service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
from backend.db import ROOT, get_write_conn, query, query_one

CCTV_DIR = ROOT / "uploads" / "cctv"
CCTV_DIR.mkdir(parents=True, exist_ok=True)

# YOLO singleton model cache
_YOLO_MODEL = None
_YOLO_DEVICE = None


def get_cctv_device() -> str:
    """Detect available accelerator: CUDA -> MPS -> CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def load_yolo_model():
    """Load Ultralytics YOLOv8n model once and cache in memory (singleton)."""
    global _YOLO_MODEL, _YOLO_DEVICE
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL, _YOLO_DEVICE

    from ultralytics import YOLO

    device = get_cctv_device()
    try:
        model = YOLO("yolov8n.pt")
        _YOLO_MODEL = model
        _YOLO_DEVICE = device
        return _YOLO_MODEL, _YOLO_DEVICE
    except Exception:
        # Fallback to CPU if GPU inference fails
        model = YOLO("yolov8n.pt")
        _YOLO_MODEL = model
        _YOLO_DEVICE = "cpu"
        return _YOLO_MODEL, "cpu"


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS.mmm string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{mins:02d}:{secs:02d}.{millis:03d}"


def process_cctv_video(
    case_id: int,
    filename: str,
    file_bytes: bytes,
    sample_rate_sec: float = 1.0,
    confidence_threshold: float = 0.50,
) -> dict:
    """
    1. Save original video to CCTV_DIR without modifying original file.
    2. Compute SHA-256 hash for forensic evidence tracking.
    3. Read video metadata via OpenCV (duration, FPS, resolution, total frames).
    4. Sample frames at sample_rate_sec interval (default 1 frame per second).
    5. Run YOLO object detection on sampled frames.
    6. Generate bounding box overlays and save visualization frame images.
    7. Save video metadata & detections into VideoEvidence & VideoDetection SQLite tables.
    """
    video_id = str(uuid.uuid4())[:8]
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    safe_name = f"{video_id}_{clean_name}"
    video_path = CCTV_DIR / safe_name
    video_path.write_bytes(file_bytes)

    # Forensic SHA-256 Hash of original file
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)

    # OpenCV metadata extraction
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {filename}. Format may be corrupted or unsupported.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration_sec = total_frames / fps if fps > 0 else 0.0

    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).strip()

    model, device = load_yolo_model()
    target_classes = {"person", "car", "motorcycle", "bicycle", "bus", "truck"}

    sampled_detections = []
    sampled_frames_meta = []

    frame_interval = max(1, int(fps * sample_rate_sec))
    curr_frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if curr_frame_idx % frame_interval == 0:
            timestamp_sec = curr_frame_idx / fps
            timestamp_str = format_timestamp(timestamp_sec)

            # Run YOLO detection on sampled frame
            results = model.predict(
                source=frame,
                device=device,
                conf=confidence_threshold,
                verbose=False,
            )

            frame_overlay = frame.copy()
            frame_detections = []

            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    cls_name = model.names.get(cls_id, str(cls_id)).lower()
                    conf = float(box.conf[0].item())

                    if cls_name in target_classes and conf >= confidence_threshold:
                        xyxy = box.xyxy[0].tolist()
                        x1, y1, x2, y2 = [int(v) for v in xyxy]

                        color = (0, 210, 255) if cls_name == "person" else (255, 149, 0)
                        cv2.rectangle(frame_overlay, (x1, y1), (x2, y2), color, 2)
                        label_str = f"{cls_name.upper()} {conf:.2f}"
                        cv2.putText(
                            frame_overlay,
                            label_str,
                            (x1, max(15, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 255),
                            1,
                            cv2.LINE_AA,
                        )

                        frame_detections.append({
                            "class": cls_name,
                            "confidence": round(conf, 2),
                            "bbox": [x1, y1, x2, y2],
                            "frame": curr_frame_idx,
                            "timestamp": timestamp_str,
                            "timestamp_sec": round(timestamp_sec, 2),
                        })

            overlay_filename = f"{video_id}_frame_{curr_frame_idx}.jpg"
            overlay_path = CCTV_DIR / overlay_filename
            cv2.imwrite(str(overlay_path), frame_overlay)

            frame_meta = {
                "frame_number": curr_frame_idx,
                "timestamp": timestamp_str,
                "timestamp_sec": round(timestamp_sec, 2),
                "overlay_url": f"/uploaded_docs/cctv/{overlay_filename}",
                "detections": frame_detections,
            }
            sampled_frames_meta.append(frame_meta)
            sampled_detections.extend(frame_detections)

        curr_frame_idx += 1

    cap.release()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Persist in VideoEvidence & VideoDetection tables
    conn = get_write_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO VideoEvidence (
                VideoID, CaseMasterID, Filename, FilePath, FileHashSHA256, FileSize,
                DurationSeconds, FPS, Width, Height, TotalFrames, Codec, Status,
                SampleRateSec, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?)
            """,
            (
                video_id,
                case_id,
                filename,
                str(video_path),
                sha256,
                file_size,
                round(duration_sec, 2),
                round(fps, 2),
                width,
                height,
                total_frames,
                codec,
                sample_rate_sec,
                now_str,
                now_str,
            ),
        )

        for f in sampled_frames_meta:
            for d in f["detections"]:
                cur.execute(
                    """
                    INSERT INTO VideoDetection (
                        VideoID, CaseMasterID, FrameNumber, TimestampStr, TimestampSeconds,
                        ClassName, Confidence, BBoxJSON, FrameOverlayPath, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video_id,
                        case_id,
                        d["frame"],
                        d["timestamp"],
                        d["timestamp_sec"],
                        d["class"],
                        d["confidence"],
                        json.dumps(d["bbox"]),
                        f["overlay_url"],
                        now_str,
                    ),
                )

        conn.commit()
    finally:
        conn.close()

    summary_counts = {}
    for d in sampled_detections:
        c = d["class"]
        summary_counts[c] = summary_counts.get(c, 0) + 1

    return {
        "video_id": video_id,
        "case_id": case_id,
        "filename": filename,
        "video_url": f"/uploaded_docs/cctv/{safe_name}",
        "file_hash_sha256": sha256,
        "file_size": file_size,
        "duration_seconds": round(duration_sec, 2),
        "duration_formatted": format_timestamp(duration_sec),
        "fps": round(fps, 2),
        "resolution": f"{width} × {height}",
        "total_frames": total_frames,
        "codec": codec,
        "device": str(device),
        "sample_rate_sec": sample_rate_sec,
        "confidence_threshold": confidence_threshold,
        "summary_counts": summary_counts,
        "total_detections": len(sampled_detections),
        "frames": sampled_frames_meta,
    }


def get_cctv_video_details(video_id: str) -> dict | None:
    """Fetch stored CCTV video record and detection timeline."""
    row = query_one(
        """
        SELECT VideoID, CaseMasterID, Filename, FilePath, FileHashSHA256, FileSize,
               DurationSeconds, FPS, Width, Height, TotalFrames, Codec, Status,
               SampleRateSec, CreatedAt, UpdatedAt
        FROM VideoEvidence WHERE VideoID = ?
        """,
        (video_id,),
    )
    if not row:
        return None

    detections = query(
        """
        SELECT FrameNumber, TimestampStr, TimestampSeconds, ClassName, Confidence,
               BBoxJSON, FrameOverlayPath
        FROM VideoDetection WHERE VideoID = ? ORDER BY FrameNumber, Confidence DESC
        """,
        (video_id,),
    )

    frames_dict = {}
    for d in detections:
        fn = d["FrameNumber"]
        if fn not in frames_dict:
            frames_dict[fn] = {
                "frame_number": fn,
                "timestamp": d["TimestampStr"],
                "timestamp_sec": d["TimestampSeconds"],
                "overlay_url": d["FrameOverlayPath"],
                "detections": [],
            }
        frames_dict[fn]["detections"].append({
            "class": d["ClassName"],
            "confidence": d["Confidence"],
            "bbox": json.loads(d["BBoxJSON"]),
            "frame": fn,
            "timestamp": d["TimestampStr"],
        })

    summary_counts = {}
    for d in detections:
        c = d["ClassName"]
        summary_counts[c] = summary_counts.get(c, 0) + 1

    return {
        "video_id": row["VideoID"],
        "case_id": row["CaseMasterID"],
        "filename": row["Filename"],
        "video_url": f"/uploaded_docs/cctv/{Path(row['FilePath'].replace('\\', '/')).name}",
        "file_hash_sha256": row["FileHashSHA256"],
        "file_size": row["FileSize"],
        "duration_seconds": row["DurationSeconds"],
        "duration_formatted": format_timestamp(row["DurationSeconds"]),
        "fps": row["FPS"],
        "resolution": f"{row['Width']} × {row['Height']}",
        "total_frames": row["TotalFrames"],
        "codec": row["Codec"],
        "status": row["Status"],
        "sample_rate_sec": row["SampleRateSec"],
        "summary_counts": summary_counts,
        "total_detections": len(detections),
        "frames": list(frames_dict.values()),
    }
