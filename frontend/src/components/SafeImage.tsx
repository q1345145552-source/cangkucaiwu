"use client";
import { useState } from "react";

/**
 * 图片加载失败自动回退：
 * - src 加载失败 → 尝试 fallbackSrc（原图）
 * - fallbackSrc 也失败 → 显示 fallback 占位（不会裂图）
 * 用法：src 传缩略图，fallbackSrc 传原图。
 */
export default function SafeImage({
  src,
  fallbackSrc,
  alt = "",
  className = "",
  onClick,
  fallback,
}: {
  src?: string;
  fallbackSrc?: string;
  alt?: string;
  className?: string;
  onClick?: (e: any) => void;
  fallback?: React.ReactNode;
}) {
  const [current, setCurrent] = useState<string | undefined>(src);
  const [failed, setFailed] = useState(false);

  if (failed || !current) {
    return <>{fallback ?? <div className={className} />}</>;
  }

  return (
    <img
      src={current}
      alt={alt}
      className={className}
      onClick={onClick}
      onError={() => {
        if (fallbackSrc && current !== fallbackSrc) {
          setCurrent(fallbackSrc);
        } else {
          setFailed(true);
        }
      }}
    />
  );
}
