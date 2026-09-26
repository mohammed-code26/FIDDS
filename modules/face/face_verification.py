"""Face verification using dlib (via face_recognition library)."""
import io
import numpy as np
import face_recognition
from PIL import Image


MATCH_THRESHOLD = 0.55
POSSIBLE_MATCH_THRESHOLD = 0.45


def _load_rgb(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def _detect_and_encode(rgb_array, label):
    locations = face_recognition.face_locations(rgb_array, model="hog")
    if not locations:
        return {"ok": False, "reason": f"No face detected in {label}.", "encodings": []}
    encodings = face_recognition.face_encodings(rgb_array, known_face_locations=locations)
    if not encodings:
        return {"ok": False, "reason": f"Face detected in {label} but encoding failed.", "encodings": []}
    return {
        "ok": True,
        "encodings": encodings,
        "locations": locations,
        "count": len(locations),
    }


def _crop_document_face_region(rgb_array):
    h, w = rgb_array.shape[:2]
    return rgb_array[0:int(h * 0.85), 0:int(w * 0.40)]


def verify_faces(document_bytes, selfie_bytes):
    result = {
        "verdict": "UNABLE TO VERIFY",
        "similarity": None,
        "threshold": MATCH_THRESHOLD,
        "possible_match_threshold": POSSIBLE_MATCH_THRESHOLD,
        "reasons": [],
        "document_faces": 0,
        "selfie_faces": 0,
    }

    try:
        doc_rgb = _load_rgb(document_bytes)
        selfie_rgb = _load_rgb(selfie_bytes)
    except Exception as e:
        result["reasons"].append(f"Could not decode image: {e}")
        return result

    doc = _detect_and_encode(doc_rgb, "document (full image)")
    if not doc["ok"]:
        cropped = _crop_document_face_region(doc_rgb)
        doc = _detect_and_encode(cropped, "document (photo region)")
        if not doc["ok"]:
            result["reasons"].append("Face could not be detected on the document.")
            return result

    result["document_faces"] = doc["count"]

    selfie = _detect_and_encode(selfie_rgb, "selfie")
    if not selfie["ok"]:
        result["reasons"].append("No face detected in the selfie.")
        return result

    result["selfie_faces"] = selfie["count"]

    if doc["count"] > 1:
        result["reasons"].append(f"Multiple faces ({doc['count']}) detected on document; ambiguous.")
        return result
    if selfie["count"] > 1:
        result["reasons"].append(f"Multiple faces ({selfie['count']}) detected in selfie; ambiguous.")
        return result

    doc_enc = doc["encodings"][0]
    selfie_enc = selfie["encodings"][0]
    distances = face_recognition.face_distance([doc_enc], selfie_enc)
    distance = float(distances[0])
    similarity = round(1.0 - distance, 4)
    result["similarity"] = similarity

    if similarity >= MATCH_THRESHOLD:
        result["verdict"] = "MATCH"
        result["reasons"].append(f"Face similarity {similarity:.2f} is above the match threshold ({MATCH_THRESHOLD}).")
    elif similarity >= POSSIBLE_MATCH_THRESHOLD:
        result["verdict"] = "POSSIBLE MATCH"
        result["reasons"].append(f"Face similarity {similarity:.2f} is between possible-match ({POSSIBLE_MATCH_THRESHOLD}) and match ({MATCH_THRESHOLD}). Manual review recommended.")
    else:
        result["verdict"] = "NO MATCH"
        result["reasons"].append(f"Face similarity {similarity:.2f} is below the possible-match threshold ({POSSIBLE_MATCH_THRESHOLD}).")

    result["reasons"].append("Face verification is a signal only. Lighting, angle, expression, and image quality can affect similarity.")
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m modules.face.face_verification <document> <selfie>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        doc_b = f.read()
    with open(sys.argv[2], "rb") as f:
        selfie_b = f.read()
    r = verify_faces(doc_b, selfie_b)
    for k, v in r.items():
        print(f"{k}: {v}")
