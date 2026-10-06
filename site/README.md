# Stake Overlay Maker

A static website for making the Stake header overlay: logo, "Stake" or "Stake.com" with the gold badge, "@Stake", and a caption, on a black or white background. It exports a 1080px-wide PNG, which is the full width of a 9:16 Reel or TikTok frame.

## Matching the Clipping Bot

The layout is measured from the Clipping Bot's own output, which is 840px wide with a 113px logo. Positions, font sizes, colours and the logo's corner radius all match it. The export is that layout scaled to 1080px wide, which gives the same 145px logo seen on approved posts.

- **Font:** the bot uses Segoe UI. Segoe UI can't be redistributed, so the page bundles Selawik, Microsoft's open-source metric-compatible version of it (SIL OFL, see `fonts/OFL-Selawik.txt`). The text looks the same on every device, including phones without Segoe UI.
- **Logo:** `assets/stake-logo-text.png` is the white wordmark at 4x resolution, cleaned up from the bot's output. The page draws the navy rounded square itself.

## Hosting

`.github/workflows/pages.yml` publishes the `site/` folder to GitHub Pages whenever `site/` changes on `main`. It only needs one setup step: in the repo, go to **Settings → Pages** and set **Source** to **GitHub Actions**.

The site is plain static files with no build step, so any static host also works: Netlify, Vercel or Cloudflare Pages, pointed at the `site/` folder.

## Files

- `index.html`: the page
- `app.js`: draws the overlay and handles download and copy
- `embedded.js`: the logo and fonts as data URIs (generated)
- `build-embedded.py`: regenerates `embedded.js`; run it after changing anything in `assets/` or `fonts/`
