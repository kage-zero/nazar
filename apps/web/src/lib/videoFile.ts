/**
 * Client-side pre-check only. The server re-validates by decoding the real content;
 * the browser's MIME type and extension are hints, never proof.
 */
export const VIDEO_EXTENSIONS = ['mp4', 'mov', 'mkv', 'avi', 'm4v'] as const;

export type VideoCheck =
  | { ok: true; name: string; sizeBytes: number; type: string }
  | { ok: false; name: string; error: string };

export function checkVideoFile(
  file: { name: string; size: number; type: string },
  maxBytes: number,
): VideoCheck {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  // The server stores uploads by extension, so the extension must be a known one.
  if (!(VIDEO_EXTENSIONS as readonly string[]).includes(ext)) {
    return {
      ok: false,
      name: file.name,
      error: `“${file.name}” is not a video. Choose an ${VIDEO_EXTENSIONS.join(', ').toUpperCase()} file.`,
    };
  }
  if (file.size === 0) {
    return { ok: false, name: file.name, error: `“${file.name}” is empty.` };
  }
  if (file.size > maxBytes) {
    return {
      ok: false,
      name: file.name,
      error: `“${file.name}” is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`,
    };
  }
  return { ok: true, name: file.name, sizeBytes: file.size, type: file.type || `video/${ext}` };
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit] ?? 'B'}`;
}
