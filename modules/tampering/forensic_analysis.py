"""Tampering analysis - ELA, metadata, JPEG grid, noise variance."""
import io
import numpy as np
import cv2
from PIL import Image, ExifTags

ELA_JPEG_QUALITY = 90
ELA_AMPLIFY = 15
THRESH_LOW = 30
THRESH_HIGH = 60


def _ela(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=ELA_JPEG_QUALITY)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    a = np.asarray(img, dtype=np.int16)
    b = np.asarray(recompressed, dtype=np.int16)
    diff = np.abs(a - b).astype(np.uint8)
    ela_gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
    ela_amplified = np.clip(ela_gray.astype(np.int32) * ELA_AMPLIFY, 0, 255).astype(np.uint8)
    mean_err = float(ela_gray.mean())
    max_err = float(ela_gray.max())
    high_mask = ela_gray > (ela_gray.mean() + 2 * ela_gray.std())
    top_ratio = float(high_mask.sum()) / ela_gray.size
    return ela_amplified, mean_err, max_err, top_ratio


def detect_ela(image_bytes):
    try:
        ela_map, mean_err, max_err, top_ratio = _ela(image_bytes)
    except Exception as e:
        return {
            "id": "T1", "name": "Error Level Analysis",
            "signal": "UNAVAILABLE", "score": 0,
            "reason": f"ELA could not be computed: {e}",
        }
    try:
        cv2.imwrite("uploads/_debug_ela.png", ela_map)
    except Exception:
        pass
    if top_ratio < 0.02:
        signal = "LOW"; score = int(top_ratio * 500)
        reason = "ELA error is uniform across the image. No localized manipulation signature."
    elif top_ratio < 0.08:
        signal = "MEDIUM"; score = int(30 + (top_ratio - 0.02) * 800)
        reason = f"ELA shows localized regions of high error ({top_ratio*100:.1f}% of pixels). Could be compression artifacts or localized edits. Requires review."
    else:
        signal = "HIGH"; score = min(100, int(60 + (top_ratio - 0.08) * 500))
        reason = f"ELA shows {top_ratio*100:.1f}% of pixels with elevated error - strong localized manipulation signal. Requires manual review."
    return {
        "id": "T1", "name": "Error Level Analysis",
        "signal": signal, "score": score, "reason": reason,
        "details": {"mean_error": round(mean_err, 2), "max_error": round(max_err, 2), "high_error_ratio": round(top_ratio, 4)},
    }


SUSPICIOUS_SOFTWARE = ["photoshop", "gimp", "affinity", "pixelmator", "paint.net", "lightroom", "capture one", "inkscape"]


def inspect_metadata(image_bytes):
    flags = []
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
    except Exception as e:
        return {
            "id": "T2", "name": "Metadata inspection",
            "signal": "UNAVAILABLE", "score": 0,
            "reason": f"Metadata could not be read: {e}",
            "metadata": {},
        }
    if not exif:
        return {
            "id": "T2", "name": "Metadata inspection",
            "signal": "LOW", "score": 10,
            "reason": "No EXIF metadata present. Common for scanned or web-exported documents - not inherently suspicious.",
            "metadata": {"has_exif": False, "flags": []},
        }
    decoded = {}
    for tag_id, value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if isinstance(value, (str, int, float)):
            decoded[tag_name] = value
        elif isinstance(value, bytes):
            decoded[tag_name] = f"<{len(value)} bytes>"
    software = str(decoded.get("Software", "")).lower()
    if software:
        for sus in SUSPICIOUS_SOFTWARE:
            if sus in software:
                flags.append(f"Editor software detected in metadata: {software}")
                break
    dt = decoded.get("DateTime")
    dto = decoded.get("DateTimeOriginal")
    if dt and dto and dt != dto:
        flags.append(f"Timestamp inconsistency: DateTime={dt}, DateTimeOriginal={dto}")
    if flags:
        return {
            "id": "T2", "name": "Metadata inspection",
            "signal": "MEDIUM", "score": 40,
            "reason": "Metadata contains signals that may indicate editing. Metadata alone does not prove manipulation - requires review.",
            "metadata": {"has_exif": True, "flags": flags, "software": decoded.get("Software"), "raw_keys": list(decoded.keys())},
        }
    return {
        "id": "T2", "name": "Metadata inspection",
        "signal": "LOW", "score": 10,
        "reason": "Metadata present with no suspicious editor or timestamp signals.",
        "metadata": {"has_exif": True, "flags": [], "software": decoded.get("Software"), "raw_keys": list(decoded.keys())},
    }


def detect_jpeg_grid(image_bytes):
    try:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"id": "T3", "name": "JPEG grid consistency", "signal": "UNAVAILABLE", "score": 0,
                    "reason": "Could not decode image for grid analysis."}
        f = img.astype(np.float32)
        diff_x = np.abs(np.diff(f, axis=1))
        diff_y = np.abs(np.diff(f, axis=0))
        col_energy = diff_x.mean(axis=0)
        row_energy = diff_y.mean(axis=1)
        bx = [i for i in range(len(col_energy)) if (i + 1) % 8 == 0]
        by = [i for i in range(len(row_energy)) if (i + 1) % 8 == 0]
        if not bx or not by:
            return {"id": "T3", "name": "JPEG grid consistency", "signal": "LOW", "score": 10,
                    "reason": "Image too small for reliable grid analysis."}
        bx_set = set(bx); by_set = set(by)
        bnd_x = np.mean([col_energy[i] for i in bx])
        off_x = np.mean([col_energy[i] for i in range(len(col_energy)) if i not in bx_set])
        bnd_y = np.mean([row_energy[i] for i in by])
        off_y = np.mean([row_energy[i] for i in range(len(row_energy)) if i not in by_set])
        ratio_x = bnd_x / (off_x + 1e-6)
        ratio_y = bnd_y / (off_y + 1e-6)
        max_ratio = max(ratio_x, ratio_y)
        if max_ratio < 1.15:
            signal = "LOW"; score = 10
            reason = "JPEG block boundaries are consistent with the surrounding image content."
        elif max_ratio < 1.4:
            signal = "MEDIUM"; score = 35
            reason = f"Slight block-boundary anomaly (ratio {max_ratio:.2f}). Could indicate recompression or splicing in one region."
        else:
            signal = "HIGH"; score = 65
            reason = f"Strong block-boundary anomaly (ratio {max_ratio:.2f}). Likely signals re-compression or localized edits. Requires review."
        return {
            "id": "T3", "name": "JPEG grid consistency",
            "signal": signal, "score": score, "reason": reason,
            "details": {"ratio_x": round(ratio_x, 3), "ratio_y": round(ratio_y, 3)},
        }
    except Exception as e:
        return {"id": "T3", "name": "JPEG grid consistency", "signal": "UNAVAILABLE", "score": 0,
                "reason": f"Grid analysis failed: {e}"}


def detect_noise_variance(image_bytes):
    try:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"id": "T4", "name": "Noise variance", "signal": "UNAVAILABLE", "score": 0,
                    "reason": "Could not decode image for noise analysis."}
        lap = cv2.Laplacian(img, cv2.CV_64F)
        residual = np.abs(lap)
        patch = 32
        h, w = residual.shape
        variances = []
        for y in range(0, h - patch + 1, patch):
            for x in range(0, w - patch + 1, patch):
                p = residual[y:y + patch, x:x + patch]
                variances.append(p.var())
        if not variances:
            return {"id": "T4", "name": "Noise variance", "signal": "LOW", "score": 10,
                    "reason": "Image too small for patch-based noise analysis."}
        v = np.array(variances)
        median_v = np.median(v)
        if median_v == 0:
            return {"id": "T4", "name": "Noise variance", "signal": "LOW", "score": 10,
                    "reason": "Zero residual variance - image appears uniform (unusual for photos but not conclusive)."}
        outlier_ratio = float((v > 3 * median_v).sum()) / len(v)
        if outlier_ratio < 0.02:
            signal = "LOW"; score = 10
            reason = "Local noise is uniform across the image. No spliced-region signature."
        elif outlier_ratio < 0.10:
            signal = "MEDIUM"; score = 35
            reason = f"{outlier_ratio*100:.1f}% of image patches show abnormal noise. Could indicate local editing or JPEG quantization variance."
        else:
            signal = "HIGH"; score = 65
            reason = f"{outlier_ratio*100:.1f}% of patches show abnormal noise - strong local-inconsistency signal. Requires review."
        return {
            "id": "T4", "name": "Noise variance",
            "signal": signal, "score": score, "reason": reason,
            "details": {"outlier_ratio": round(outlier_ratio, 4), "patch_size": patch},
        }
    except Exception as e:
        return {"id": "T4", "name": "Noise variance", "signal": "UNAVAILABLE", "score": 0,
                "reason": f"Noise analysis failed: {e}"}


def run_tampering_analysis(image_bytes):
    detectors = [
        detect_ela(image_bytes),
        inspect_metadata(image_bytes),
        detect_jpeg_grid(image_bytes),
        detect_noise_variance(image_bytes),
    ]
    weights = {"T1": 0.35, "T2": 0.15, "T3": 0.25, "T4": 0.25}
    weighted = 0.0
    for d in detectors:
        weighted += d["score"] * weights.get(d["id"], 0.2)
    score = int(round(weighted))
    if score < THRESH_LOW:
        overall = "LOW"
    elif score < THRESH_HIGH:
        overall = "MEDIUM"
    else:
        overall = "HIGH"
    meta_det = next((d for d in detectors if d["id"] == "T2"), {})
    metadata = meta_det.get("metadata", {})
    return {"overall": overall, "score": score, "detectors": detectors, "metadata": metadata}
