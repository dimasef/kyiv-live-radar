const SIZE = 64;
const PERIOD_MS = 3000;
const FRAME_MS = 100; // 10fps — smooth enough for a slow 3s pulse, cheap on CPU

function drawFrame(ctx: CanvasRenderingContext2D, t: number) {
  const s = SIZE;
  ctx.clearRect(0, 0, s, s); // transparent background — reads fine in dark/light tabs alike

  const cx = s / 2;
  const cy = s / 2;
  for (let i = 0; i < 3; i++) {
    const phase = ((t + i * (PERIOD_MS / 3)) % PERIOD_MS) / PERIOD_MS;
    const radius = 12 + phase * 18;
    const opacity = 0.6 * (1 - phase);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(103, 232, 249, ${opacity.toFixed(3)})`;
    ctx.lineWidth = 5;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(cx, cy, 10, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(103, 232, 249, 0.95)";
  ctx.fill();
}

function setFaviconHref(dataUrl: string) {
  document.querySelectorAll('link[rel="icon"]').forEach((el) => el.remove());
  const link = document.createElement("link");
  link.rel = "icon";
  link.type = "image/png";
  link.href = dataUrl;
  document.head.appendChild(link);
}

export function startAnimatedFavicon(): void {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const start = performance.now();
  setInterval(() => {
    drawFrame(ctx, performance.now() - start);
    setFaviconHref(canvas.toDataURL("image/png"));
  }, FRAME_MS);
}
