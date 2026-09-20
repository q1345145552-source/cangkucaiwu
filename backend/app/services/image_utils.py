"""图片上传统一处理：压缩 + 缩略图。

规则：
- 图片最长边超过 1600px 等比缩到 1600，存 JPEG 质量 85。
- 压缩后若比原文件更大，保留原图。
- 压缩失败不抛错，用原图。
- PDF/非图片原样保存，不生成缩略图。
- 每张图片额外生成一张缩略图：最长边 300px、质量 80，文件名加 _thumb 后缀。
"""
import os
import io
from PIL import Image

DEFAULT_UPLOAD_DIR = "/app/uploads"


def _to_jpeg_bytes(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _resize_to_max(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        ratio = max_side / float(longest)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    return img


def _compress(content: bytes, max_side: int, quality: int):
    """压缩图片，失败返回 None。"""
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
        img = _resize_to_max(img, max_side)
        return _to_jpeg_bytes(img, quality)
    except Exception:
        return None


def is_image(content: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
        return True
    except Exception:
        return False


def save_image(content: bytes, abs_subdir: str, rel_subdir: str, fname: str) -> dict:
    """保存上传图片并压缩、生成缩略图。

    abs_subdir: 文件系统绝对目录，如 /app/uploads/4/2026-09-20/employee_photos
    rel_subdir: 相对 URL 目录，如 uploads/4/2026-09-20/employee_photos
    fname: 原始文件名（含扩展名），如 abc123.jpg
    返回 {"path": 主图相对路径, "thumb_path": 缩略图相对路径(可能为 None), "size": 字节数}
    """
    os.makedirs(abs_subdir, exist_ok=True)

    is_img = is_image(content)

    main_bytes = content
    main_name = fname
    if is_img:
        compressed = _compress(content, 1600, 85)
        # 压缩后更小才用压缩版，否则保留原图
        if compressed is not None and len(compressed) < len(content):
            main_bytes = compressed
            base, _ = os.path.splitext(fname)
            main_name = f"{base}.jpg"

    with open(os.path.join(abs_subdir, main_name), "wb") as f:
        f.write(main_bytes)

    thumb_name = None
    if is_img:
        thumb = _compress(content, 300, 80)
        if thumb is not None:
            base, _ = os.path.splitext(main_name)
            thumb_name = f"{base}_thumb.jpg"
            with open(os.path.join(abs_subdir, thumb_name), "wb") as f:
                f.write(thumb)

    return {
        "path": f"{rel_subdir}/{main_name}",
        "thumb_path": f"{rel_subdir}/{thumb_name}" if thumb_name else None,
        "size": len(main_bytes),
        "is_image": is_img,
    }


def thumb_path_of(path: str) -> str:
    """由主图相对路径推导缩略图相对路径（缩略图恒为 _thumb.jpg）。"""
    if not path:
        return ""
    base, _ = os.path.splitext(path)
    return f"{base}_thumb.jpg"
