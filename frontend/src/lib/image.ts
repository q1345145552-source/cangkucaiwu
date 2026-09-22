/** 由原图路径推导缩略图路径（与后端 thumb_path_of 一致：去掉扩展名 + _thumb.jpg）。 */
export function thumbPathOf(path?: string | null): string {
  if (!path) return "";
  const lastSlash = path.lastIndexOf("/");
  const lastDot = path.lastIndexOf(".");
  // 只有最后一个 "/" 之后的点才算扩展名（避免目录名里的点被误判）
  if (lastDot > lastSlash) {
    return path.slice(0, lastDot) + "_thumb.jpg";
  }
  return path + "_thumb.jpg";
}
