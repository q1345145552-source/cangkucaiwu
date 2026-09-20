"""批量压缩已有照片并生成缩略图（幂等，可重复运行）。

用法：在 backend 容器内执行
  python scripts/compress_existing_images.py

扫描 UPLOAD_DIR 下所有图片：
- 主图 > 1MB 的压缩（最长边1600/质量85），压缩后更小才覆盖。
- 每张图片生成 _thumb.jpg 缩略图（最长边300/质量80），已存在则跳过。
- 输出处理张数、生成缩略图张数、节省空间。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.image_utils import _compress, is_image  # noqa: E402

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def main():
    if not os.path.isdir(UPLOAD_DIR):
        print(f"UPLOAD_DIR 不存在: {UPLOAD_DIR}")
        sys.exit(1)

    total = 0
    compressed = 0
    thumbs = 0
    saved_bytes = 0

    for root, _dirs, files in os.walk(UPLOAD_DIR):
        for name in files:
            base, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in IMAGE_EXTS:
                continue
            if base.endswith("_thumb"):
                continue
            path = os.path.join(root, name)
            total += 1
            try:
                with open(path, "rb") as f:
                    content = f.read()
            except Exception:
                continue
            if not is_image(content):
                continue

            size_before = len(content)

            # 生成缩略图（不存在才生成）
            thumb_path = os.path.join(root, f"{base}_thumb.jpg")
            if not os.path.exists(thumb_path):
                t = _compress(content, 300, 80)
                if t is not None:
                    with open(thumb_path, "wb") as f:
                        f.write(t)
                    thumbs += 1

            # 主图 > 1MB 压缩
            if size_before > 1024 * 1024:
                c = _compress(content, 1600, 85)
                if c is not None and len(c) < size_before:
                    with open(path, "wb") as f:
                        f.write(c)
                    compressed += 1
                    saved_bytes += size_before - len(c)

    print("=" * 50)
    print(f"扫描图片: {total} 张")
    print(f"压缩主图: {compressed} 张")
    print(f"生成缩略图: {thumbs} 张")
    print(f"节省空间: {saved_bytes / (1024 * 1024):.2f} MB")
    print("=" * 50)


if __name__ == "__main__":
    main()
