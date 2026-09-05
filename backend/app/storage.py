"""
Real object storage, backed by local disk instead of S3 — architecturally
the same shape as the real thing (a signed, time-limited upload URL that
doesn't require auth to PUT to, then a content-integrity check against what
was claimed at capture time), just swap `save_file`/`read_file`/
`generate_upload_token` for boto3 S3 calls and a CloudFront-signed URL to
point this at real S3 without touching any router code.

The integrity check this closes is real and was a real gap before this
existed: `POST /v1/captures/init` lets a client *claim* a content_hash, but
nothing previously verified the uploaded bytes actually hashed to that
value. A technician (or a compromised client) could claim any hash and the
verification engine would trust it. Now the claimed hash is checked against
the real SHA-256 of the real uploaded bytes, and a mismatch is rejected
before the capture can ever be marked verified.
"""
import hashlib
import hmac
import os
import time

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

UPLOAD_TOKEN_SECRET = os.environ.get("FPC_UPLOAD_SECRET", "dev-upload-secret-change-in-production")
UPLOAD_TOKEN_TTL_SECONDS = 300


def generate_upload_token(capture_id: str) -> str:
    """A signed, time-limited token embedded in the upload URL — this is
    what lets the technician app PUT bytes without a bearer token on that
    specific request (matching how real S3 pre-signed URLs work: the
    signature itself is the authorization), while still preventing anyone
    who doesn't have this exact URL from uploading to a capture they don't
    own."""
    expires_at = int(time.time()) + UPLOAD_TOKEN_TTL_SECONDS
    message = f"{capture_id}:{expires_at}"
    sig = hmac.new(UPLOAD_TOKEN_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{expires_at}.{sig}"


def verify_upload_token(capture_id: str, token: str) -> bool:
    try:
        expires_at_str, sig = token.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False
    if time.time() > expires_at:
        return False
    message = f"{capture_id}:{expires_at}"
    expected_sig = hmac.new(UPLOAD_TOKEN_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def _path_for(capture_id: str) -> str:
    # capture IDs are server-generated (gen_id) and never contain path
    # separators, but a defensive check costs nothing and rules out any
    # path-traversal surface entirely rather than trusting the format.
    safe_id = "".join(c for c in capture_id if c.isalnum() or c == "-")
    return os.path.join(MEDIA_DIR, f"{safe_id}.bin")


def save_file(capture_id: str, content: bytes) -> str:
    """Writes real bytes to disk and returns the REAL sha256 of what was
    actually written — this is what gets compared against the claimed
    content_hash from /captures/init, not trusted from the upload request."""
    path = _path_for(capture_id)
    with open(path, "wb") as f:
        f.write(content)
    return "sha256:" + hashlib.sha256(content).hexdigest()


def read_file(capture_id: str) -> bytes | None:
    path = _path_for(capture_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def file_exists(capture_id: str) -> bool:
    return os.path.exists(_path_for(capture_id))
