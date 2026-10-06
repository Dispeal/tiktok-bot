# Stake Overlay Maker

A static website for making the Stake header overlay: logo, "Stake" or "Stake.com" with the gold badge, "@Stake", and your caption, on a black or white background. It exports a 1080px-wide PNG to place directly above your clip.

## Run it

You don't need a build step. Open `index.html` in a browser, or host the `site/` folder on any static host (GitHub Pages, Netlify, Vercel, Cloudflare Pages).

## Files

- `index.html`: the page and its styles
- `app.js`: draws the overlay on a canvas and handles download and copy
- `assets/stake-logo.png`: the logo
- `logo-data.js`: the same logo embedded as a data URI, so the page also works when opened straight from disk

To swap in a higher-resolution official logo, replace `assets/stake-logo.png` and regenerate `logo-data.js`:

```sh
python3 -c "import base64;d=base64.b64encode(open('assets/stake-logo.png','rb').read()).decode();open('logo-data.js','w').write('window.STAKE_LOGO = \"data:image/png;base64,'+d+'\";\n')"
```
