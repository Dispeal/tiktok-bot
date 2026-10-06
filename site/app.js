// Draws the Stake header overlay on a canvas.
//
// Layout numbers are in "bot pixels": the official Clipping Bot renders the
// header on an 840px-wide canvas with a 113px logo. Every position below was
// measured from the bot's own output, then the whole thing is scaled to the
// export width (1080px = full width of a 9:16 Reel/TikTok frame, which gives
// the same 145px logo seen on approved posts).

const BOT_WIDTH = 840;
const OUTPUT_WIDTH = 1080;

const L = {
  logoX: 40,
  logoY: 39,
  logoSize: 113,
  logoRadius: 13,
  logoBg: "#071724",

  nameSize: 37,
  nameInkX: 134,          // left edge of the "S", relative to logoX
  nameBaseline: 45.5,     // relative to logoY
  // Left ink edge of each letter of "Stake.com", relative to the "S".
  nameLetterX: [0, 20, 36, 58, 78, 101, 111, 130, 155],

  badgeGap: 17,           // name ink right -> badge left
  badgeSize: 29,
  badgeCenterY: 36,       // relative to logoY

  handleSize: 39,
  handleInkX: 131,        // left edge of the "@", relative to logoX
  handleBaseline: 95.5,   // relative to logoY

  captionSize: 44,
  captionBaseline: 199,   // first line, relative to logoY
  captionLineHeight: 50,
  captionMaxWidth: 760,
  bottomPad: 54,          // last caption baseline -> bottom edge
  emptyBottomPad: 39,     // logo bottom -> bottom edge when there's no caption
};

const THEMES = {
  black: { bg: "#000000", name: "#ffffff", handle: "#c4c4c4", caption: "#ffffff" },
  white: { bg: "#ffffff", name: "#000000", handle: "#676767", caption: "#000000" },
};

const EMOJI_FONTS = '"Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif';

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const captionEl = document.getElementById("caption");
const statusEl = document.getElementById("status");

const logoText = new Image();
logoText.src = window.EMBEDDED.logoText;

function settings() {
  return {
    name: document.querySelector('input[name="name"]:checked').value,
    theme: THEMES[document.querySelector('input[name="theme"]:checked').value],
    caption: captionEl.value,
  };
}

function font(weight, size) {
  return `${weight} ${size}px "Selawik", ${EMOJI_FONTS}`;
}

// Word-wrap text to maxWidth, keeping the user's own line breaks.
function wrapLines(text, maxWidth) {
  const lines = [];
  for (const para of text.replace(/\s+$/, "").split("\n")) {
    const words = para.split(/[ \t]+/).filter(Boolean);
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

// Draw text so its ink (not its origin) starts at inkX. Returns the ink right edge.
function fillTextAtInk(text, inkX, baseline) {
  const m = ctx.measureText(text);
  const originX = inkX + m.actualBoundingBoxLeft;
  ctx.fillText(text, originX, baseline);
  return originX + m.actualBoundingBoxRight;
}

// Gold scalloped "verified" badge with a white check, in bot pixels.
function drawBadge(cx, cy, size) {
  const R = size / 2;
  const points = 12;
  ctx.save();
  ctx.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const a = (Math.PI * i) / points - Math.PI / 2;
    const r = i % 2 === 0 ? R * 0.93 : R * 0.78;
    const x = cx + Math.cos(a) * r;
    const y = cy + Math.sin(a) * r;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.closePath();
  const grad = ctx.createLinearGradient(cx, cy - R, cx, cy + R);
  grad.addColorStop(0, "#f3cd45");
  grad.addColorStop(1, "#dba214");
  ctx.fillStyle = grad;
  ctx.strokeStyle = grad;
  ctx.lineJoin = "round";
  ctx.lineWidth = R * 0.14;
  ctx.fill();
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(cx - R * 0.36, cy + R * 0.04);
  ctx.lineTo(cx - R * 0.1, cy + R * 0.3);
  ctx.lineTo(cx + R * 0.38, cy - R * 0.24);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = R * 0.2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.restore();
}

function render() {
  const { name, theme, caption } = settings();

  ctx.font = font(400, L.captionSize);
  const lines = caption.trim() ? wrapLines(caption, L.captionMaxWidth) : [];

  const heightBot = lines.length
    ? L.logoY + L.captionBaseline + (lines.length - 1) * L.captionLineHeight + L.bottomPad
    : L.logoY + L.logoSize + L.emptyBottomPad;

  const k = OUTPUT_WIDTH / BOT_WIDTH;
  canvas.width = OUTPUT_WIDTH;
  canvas.height = Math.round(heightBot * k);

  // From here on, draw in bot pixels.
  ctx.setTransform(k, 0, 0, k, 0, 0);
  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, BOT_WIDTH, heightBot);
  ctx.textBaseline = "alphabetic";

  // Logo: navy rounded square + white wordmark
  roundedRect(L.logoX, L.logoY, L.logoSize, L.logoSize, L.logoRadius);
  ctx.fillStyle = L.logoBg;
  ctx.fill();
  if (logoText.complete && logoText.naturalWidth) {
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(logoText, L.logoX, L.logoY, L.logoSize, L.logoSize);
  }

  // Name, letter by letter at the bot's exact positions
  ctx.font = font(700, L.nameSize);
  ctx.fillStyle = theme.name;
  const nameInkX = L.logoX + L.nameInkX;
  const nameBaseline = L.logoY + L.nameBaseline;
  let inkRight = nameInkX;
  [...name].forEach((ch, i) => {
    inkRight = fillTextAtInk(ch, nameInkX + L.nameLetterX[i], nameBaseline);
  });

  drawBadge(
    inkRight + L.badgeGap + L.badgeSize / 2,
    L.logoY + L.badgeCenterY,
    L.badgeSize
  );

  // Handle
  ctx.font = font(400, L.handleSize);
  ctx.fillStyle = theme.handle;
  fillTextAtInk("@Stake", L.logoX + L.handleInkX, L.logoY + L.handleBaseline);

  // Caption
  ctx.font = font(400, L.captionSize);
  ctx.fillStyle = theme.caption;
  lines.forEach((line, i) => {
    ctx.fillText(line, L.logoX, L.logoY + L.captionBaseline + i * L.captionLineHeight);
  });

  ctx.setTransform(1, 0, 0, 1, 0, 0);
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
logoText.addEventListener("load", render);

// Load the bundled fonts before the first real render so the text matches the bot.
Promise.all([
  new FontFace("Selawik", `url(${window.EMBEDDED.fontRegular})`, { weight: "400" }).load(),
  new FontFace("Selawik", `url(${window.EMBEDDED.fontBold})`, { weight: "700" }).load(),
]).then((faces) => {
  faces.forEach((f) => document.fonts.add(f));
  render();
}, render);
render();
