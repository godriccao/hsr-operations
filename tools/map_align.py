"""Project a point between two saved views of the same map floor."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def map_features(path, region):
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE) if encoded.size else None
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")

    height, width = image.shape
    if region is None:
        region = (round(0.14 * width), round(0.14 * height), round(0.71 * width), round(0.86 * height))
    left, top, right, bottom = region
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError(f"Invalid map rectangle for {path}: {region}")
    mask = np.zeros_like(image)
    mask[top:bottom, left:right] = 255
    detector = cv2.SIFT_create(nfeatures=1000, contrastThreshold=0.025)
    keypoints, descriptors = detector.detectAndCompute(image, mask)
    return keypoints, descriptors, width, height


def align(reference, actual, point, reference_region=None, actual_region=None):
    ref_keys, ref_desc, ref_width, ref_height = map_features(reference, reference_region)
    actual_keys, actual_desc, actual_width, actual_height = map_features(actual, actual_region)
    if not (0 <= point[0] < ref_width and 0 <= point[1] < ref_height):
        raise ValueError("The point is outside the reference image")
    if ref_desc is None or actual_desc is None:
        return {"status": "insufficient_match"}

    matches = cv2.BFMatcher().knnMatch(ref_desc, actual_desc, k=2)
    candidates = []
    for pair in matches:
        if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance:
            candidates.append(pair[0])

    unique_targets = {}
    for match in sorted(candidates, key=lambda item: item.distance):
        unique_targets.setdefault(match.trainIdx, match)
    if len(unique_targets) < 25:
        return {"status": "insufficient_match"}

    source = np.float32([ref_keys[match.queryIdx].pt for match in unique_targets.values()])
    destination = np.float32([actual_keys[index].pt for index in unique_targets])
    matrix, inliers = cv2.estimateAffinePartial2D(source, destination, ransacReprojThreshold=2.0)
    if matrix is None:
        return {"status": "insufficient_match"}

    good = inliers.ravel().astype(bool)
    count = int(good.sum())
    scale = float(np.linalg.norm(matrix[0, :2]))
    angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
    if count < 25 or good.mean() < 0.5 or not 0.4 <= scale <= 2.5 or abs(angle) > 2:
        return {"status": "insufficient_match"}
    span = np.ptp(source[good], axis=0)
    if span[0] < ref_width * 0.13 or span[1] < ref_height * 0.13:
        return {"status": "insufficient_match"}

    target = matrix @ [*point, 1]
    hull = cv2.convexHull(source[good])
    if cv2.pointPolygonTest(hull, tuple(point), False) < 0:
        return {"status": "point_outside_matched_area"}
    if not (0 <= target[0] < actual_width and 0 <= target[1] < actual_height):
        return {"status": "point_outside_actual_image"}

    residual = cv2.transform(source[good][None], matrix)[0] - destination[good]
    median_error = float(np.median(np.linalg.norm(residual, axis=1)))
    return {
        "status": "aligned",
        "point": np.round(target, 1).tolist(),
        "inliers": count,
        "scale": round(scale, 3),
        "median_residual_px": round(median_error, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("x", type=float)
    parser.add_argument("y", type=float)
    rect_options = {"type": int, "nargs": 4, "metavar": ("LEFT", "TOP", "RIGHT", "BOTTOM")}
    parser.add_argument("--reference-region", **rect_options)
    parser.add_argument("--actual-region", **rect_options)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    try:
        result = align(args.reference, args.actual, (args.x, args.y), args.reference_region, args.actual_region)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result))
    return 0 if result["status"] == "aligned" else 1


if __name__ == "__main__":
    raise SystemExit(main())
