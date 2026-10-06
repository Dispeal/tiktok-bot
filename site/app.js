// Draws the Stake header overlay on a canvas.
// All layout numbers are in "reference units", measured from the official
// 614px-wide header example, then scaled up to the output width.

const OUTPUT_WIDTH = 1080;
const REF_WIDTH = 614;

const L = {
  padX: 27,
  logoY: 20,
  logoSize: 113,
  logoRadius: 20,
  nameX: 161,
  nameSize: 40,
  nameBaseline: 65,
  badgeSize: 30,
  badgeGap: 16,
  badgeCenterY: 55.5,
  handleSize: 36,
  handleBaseline: 112,
  captionSize: 36,
  captionLineHeight: 48,
  captionGap: 36,     // logo bottom -> top of caption text
  captionCap: 27,     // cap height, used to place the first baseline
  bottomPad: 40,
  emptyBottomPad: 22,
};

const THEMES = {
  black: { bg: "#000000", name: "#ffffff", handle: "#c4c4c4", caption: "#ffffff" },
  white: { bg: "#ffffff", name: "#000000", handle: "#676767", caption: "#000000" },
};

const FONT_STACK = '"Segoe UI", "Open Sans", Arial, sans-serif';

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const captionEl = document.getElementById("caption");
const statusEl = document.getElementById("status");

const logo = new Image();
logo.src = window.STAKE_LOGO || "assets/stake-logo.png";

function settings() {
  return {
    name: document.querySelector('input[name="name"]:checked').value,
    theme: THEMES[document.querySelector('input[name="theme"]:checked').value],
    caption: captionEl.value,
  };
}

function font(weight, size) {
  return `${weight} ${size}px ${FONT_STACK}`;
}

// Word-wrap text to maxWidth, keeping the user's own line breaks.
function wrapLines(text, maxWidth) {
  const lines = [];
  for (const para of text.replace(/\s+$/, "").split("\n")) {
    const words = para.split(/\s+/).filter(Boolean);
    if (words.length === 0) { lines.push(""); continue; }
    let line = "";
    for (const word of words) {
      const test = line ? line + " " + word : word;
      if (ctx.measureText(test).width <= maxWidth || !line) {
        line = test;
      } else {
        lines.push(line);
        line = word;
      }
    }
    lines.push(line);
  }
  return lines;
}

function roundedRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// Gold scalloped "verified" badge with a white check.
function drawBadge(cx, cy, size) {
  const R = size / 2;
  const points = 12;
  ctx.save();
  ctx.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const a = (Math.PI * i) / points - Math.PI / 2;
    const r = i % 2 === 0 ? R * 0.92 : R * 0.76;
    const x = cx + Math.cos(a) * r;
    const y = cy + Math.sin(a) * r;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.closePath();
  const grad = ctx.createLinearGradient(cx, cy - R, cx, cy + R);
  grad.addColorStop(0, "#f6d24e");
  grad.addColorStop(1, "#d99c10");
  ctx.fillStyle = grad;
  ctx.strokeStyle = grad;
  ctx.lineJoin = "round";
  ctx.lineWidth = R * 0.16;
  ctx.fill();
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(cx - R * 0.36, cy + R * 0.02);
  ctx.lineTo(cx - R * 0.1, cy + R * 0.28);
  ctx.lineTo(cx + R * 0.38, cy - R * 0.26);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = R * 0.17;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.restore();
}

function render() {
  const { name, theme, caption } = settings();
  const k = OUTPUT_WIDTH / REF_WIDTH;

  ctx.font = font(400, L.captionSize * k);
  const lines = caption.trim()
    ? wrapLines(caption, (REF_WIDTH - L.padX * 2) * k)
    : [];

  const logoBottom = L.logoY + L.logoSize;
  let heightRef;
  if (lines.length) {
    const lastBaseline = logoBottom + L.captionGap + L.captionCap + (lines.length - 1) * L.captionLineHeight;
    heightRef = lastBaseline + L.bottomPad;
  } else {
    heightRef = logoBottom + L.emptyBottomPad;
  }

  canvas.width = OUTPUT_WIDTH;
  canvas.height = Math.round(heightRef * k);

  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Logo
  ctx.save();
  roundedRect(L.padX * k, L.logoY * k, L.logoSize * k, L.logoSize * k, L.logoRadius * k);
  ctx.fillStyle = "#071724";
  ctx.fill();
  ctx.clip();
  if (logo.complete && logo.naturalWidth) {
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(logo, L.padX * k, L.logoY * k, L.logoSize * k, L.logoSize * k);
  }
  ctx.restore();

  // Name + badge
  ctx.textBaseline = "alphabetic";
  ctx.font = font(700, L.nameSize * k);
  ctx.fillStyle = theme.name;
  ctx.fillText(name, L.nameX * k, L.nameBaseline * k);
  const nameWidth = ctx.measureText(name).width;
  drawBadge(
    L.nameX * k + nameWidth + (L.badgeGap + L.badgeSize / 2) * k,
    L.badgeCenterY * k,
    L.badgeSize * k
  );

  // Handle
  ctx.font = font(400, L.handleSize * k);
  ctx.fillStyle = theme.handle;
  ctx.fillText("@Stake", L.nameX * k, L.handleBaseline * k);

  // Caption
  ctx.font = font(400, L.captionSize * k);
  ctx.fillStyle = theme.caption;
  let y = logoBottom + L.captionGap + L.captionCap;
  for (const line of lines) {
    ctx.fillText(line, L.padX * k, y * k);
    y += L.captionLineHeight;
  }
}

function setStatus(msg) {
  statusEl.textContent = msg;
  clearTimeout(setStatus.t);
  setStatus.t = setTimeout(() => (statusEl.textContent = ""), 3000);
}

function toBlob() {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

document.getElementById("download").addEventListener("click", async () => {
  render();
  const blob = await toBlob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "stake-overlay.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus("Downloaded.");
});

document.getElementById("copy").addEventListener("click", async () => {
  render();
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": toBlob() })]);
    setStatus("Copied to clipboard.");
  } catch {
    setStatus("Your browser can't copy images. Use Download instead.");
  }
});

document.querySelectorAll("input[type=radio]").forEach((el) => el.addEventListener("change", render));
captionEl.addEventListener("input", render);
logo.addEventListener("load", render);

render();
// Re-render once web fonts are ready so text metrics are correct.
Promise.all([
  document.fonts.load(font(400, 36)),
  document.fonts.load(font(700, 40)),
]).then(render, render);
document.fonts.ready.then(render);
