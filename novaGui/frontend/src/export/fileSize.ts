/* ========================================
   FILE SIZE
   A byte count as the Export dialog writes it: 512 B, 12.4 KB, 3.1 MB.
   Sean Bowman [11/19/2026]
   ======================================== */

export function formatSize(byteCount: number): string {
    let value = byteCount;
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
        if (value < 1024 || unit === 'GB') {
            return unit === 'B' ? `${value.toFixed(0)} B` : `${value.toFixed(1)} ${unit}`;
        }
        value /= 1024;
    }
    return `${value.toFixed(1)} GB`;
}
