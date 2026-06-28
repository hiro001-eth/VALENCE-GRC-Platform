#!/usr/bin/env python3
"""VALENCE GRC — Advanced enterprise demo recorder → advance_demo.mp4 (4K)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import record_demo as rd
from record_demo import (
    BASE_URL,
    DEMO_SECTIONS,
    OUTPUT_H,
    OUTPUT_W,
    RECORD_H,
    RECORD_W,
    convert_to_4k_mp4,
    pause,
)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_MP4 = ROOT / "advance_demo.mp4"
VIDEO_TMP = ROOT / ".advance_demo_tmp"

# ── Enhanced overlay injectors (premium sales-demo styling) ──────────────────

rd.INJECT_CHAPTER = """
(args) => {
  const [num, total, title, subtitle, bullets, footer, tagline] = args;
  document.getElementById('valence-demo-chapter')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-chapter';
  el.style.cssText = `
    position:fixed;inset:0;z-index:100000;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    background:radial-gradient(ellipse at 50% 0%,#1a3d38 0%,#0a0e14 45%,#030508 100%);
    font-family:'IBM Plex Sans',system-ui,sans-serif;color:#e8e6e1;padding:48px;
  `;
  const pct = Math.round((parseInt(num) / parseInt(total)) * 100);
  const list = (bullets || []).map(b =>
    `<li style="margin:16px 0;padding:14px 18px;line-height:1.55;color:#d1dae6;font-size:21px;
      background:rgba(18,107,99,.08);border-left:3px solid #126B63;border-radius:0 6px 6px 0">
      ${b}</li>`
  ).join('');
  el.innerHTML = `
    <div style="max-width:1140px;text-align:center;width:100%">
      <div style="display:flex;justify-content:center;gap:12px;margin-bottom:32px;flex-wrap:wrap">
        <span style="padding:8px 18px;border:1px solid rgba(94,234,212,.4);border-radius:20px;
          color:#5eead4;font-size:12px;letter-spacing:.16em;text-transform:uppercase">
          Advanced Demo · Enterprise Edition
        </span>
        <span style="padding:8px 18px;background:rgba(18,107,99,.2);border-radius:20px;
          color:#a7f3d0;font-size:12px;letter-spacing:.12em">
          Section ${num} of ${total}
        </span>
      </div>
      <div style="height:4px;background:rgba(255,255,255,.08);border-radius:2px;margin:0 auto 36px;max-width:600px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#126B63,#5eead4);border-radius:2px"></div>
      </div>
      <h1 style="font-size:56px;font-weight:700;margin:0 0 18px;letter-spacing:-.03em;line-height:1.08;
        background:linear-gradient(135deg,#fff 0%,#94a3b8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent">
        ${title}
      </h1>
      <p style="font-size:26px;color:#94a3b8;line-height:1.5;margin:0 auto 32px;max-width:860px;font-weight:400">${subtitle}</p>
      ${tagline ? `<p style="font-size:18px;color:#5eead4;margin:0 auto 28px;max-width:720px;font-style:italic">${tagline}</p>` : ''}
      <ul style="list-style:none;padding:0;margin:0 auto;text-align:left;max-width:820px">${list}</ul>
      <p style="margin-top:44px;font-size:13px;color:#64748b;letter-spacing:.08em;text-transform:uppercase">${footer}</p>
    </div>`;
  document.body.appendChild(el);
}
"""

rd.INJECT_EXPLAIN = """
(args) => {
  const [title, body, highlights, badge, bestCase] = args;
  document.getElementById('valence-demo-explain')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-explain';
  el.style.cssText = `
    position:fixed;inset:0;z-index:99998;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    background:rgba(3,6,10,.82);backdrop-filter:blur(4px);
    font-family:'IBM Plex Sans',system-ui,sans-serif;padding:40px;
  `;
  const hi = (highlights || []).map(h =>
    `<div style="display:flex;gap:14px;align-items:flex-start;margin:14px 0;padding:12px 16px;
      background:rgba(255,255,255,.03);border-radius:6px">
      <span style="color:#5eead4;font-weight:700;font-size:20px;flex-shrink:0">◆</span>
      <span style="color:#e2e8f0;font-size:18px;line-height:1.5">${h}</span></div>`
  ).join('');
  const bc = bestCase ? `
    <div style="margin-top:28px;padding:20px 24px;background:linear-gradient(135deg,rgba(18,107,99,.25),rgba(94,234,212,.08));
      border:1px solid rgba(94,234,212,.35);border-radius:8px">
      <div style="color:#fcd34d;font-size:11px;letter-spacing:.2em;text-transform:uppercase;margin-bottom:8px;font-weight:600">
        ★ Best Case Outcome
      </div>
      <p style="color:#ecfdf5;font-size:17px;line-height:1.55;margin:0;font-weight:500">${bestCase}</p>
    </div>` : '';
  el.innerHTML = `
    <div style="max-width:920px;background:linear-gradient(180deg,#161b24 0%,#0f1318 100%);
      border:1px solid rgba(18,107,99,.4);border-radius:10px;padding:48px 52px;
      box-shadow:0 32px 100px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.06)">
      <div style="display:inline-block;padding:6px 14px;background:rgba(18,107,99,.3);
        border-radius:4px;color:#5eead4;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-bottom:18px">
        ${badge}
      </div>
      <h2 style="color:#fff;font-size:38px;font-weight:700;margin:0 0 18px;line-height:1.15;letter-spacing:-.02em">${title}</h2>
      <p style="color:#94a3b8;font-size:20px;line-height:1.6;margin:0 0 28px">${body}</p>
      <div>${hi}</div>
      ${bc}
    </div>`;
  document.body.appendChild(el);
}
"""

rd.INJECT_CAPTION = """
(args) => {
  const [text] = args;
  document.getElementById('valence-demo-caption')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-caption';
  el.style.cssText = `
    position:fixed;bottom:0;left:0;right:0;z-index:99997;pointer-events:none;
    padding:24px 56px 32px;
    background:linear-gradient(transparent 0%,rgba(0,0,0,.75) 40%,rgba(0,0,0,.92) 100%);
    font-family:'IBM Plex Mono',monospace;font-size:18px;color:#5eead4;text-align:center;
    letter-spacing:.05em;line-height:1.5;
  `;
  el.innerHTML = `<span style="opacity:.7;margin-right:12px">▸</span>${text}`;
  document.body.appendChild(el);
}
"""

rd.INJECT_SECURITY_TEST = """
(args) => {
  const [step, title, checks, verdict] = args;
  document.getElementById('valence-demo-security-test')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-security-test';
  el.style.cssText = `
    position:fixed;top:28px;right:28px;z-index:99999;pointer-events:none;
    max-width:440px;background:linear-gradient(145deg,#0c1218,#141c26);
    border:2px solid #126B63;border-radius:10px;padding:26px 30px;
    font-family:'IBM Plex Sans',system-ui,sans-serif;
    box-shadow:0 20px 60px rgba(0,0,0,.7),0 0 0 1px rgba(94,234,212,.1);
  `;
  const items = (checks || []).map(c =>
    `<div style="display:flex;gap:12px;align-items:flex-start;margin:12px 0">
      <span style="display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;
        background:rgba(34,197,94,.2);border-radius:50%;color:#4ade80;font-weight:700;font-size:13px;flex-shrink:0">✓</span>
      <span style="color:#e2e8f0;font-size:15px;line-height:1.45">${c}</span></div>`
  ).join('');
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span style="width:8px;height:8px;background:#22c55e;border-radius:50%;box-shadow:0 0 8px #22c55e"></span>
      <span style="color:#5eead4;font-size:11px;letter-spacing:.2em;text-transform:uppercase;font-weight:600">
        Security Engineer Verification · ${step}
      </span>
    </div>
    <h3 style="color:#fff;font-size:21px;font-weight:700;margin:0 0 16px;line-height:1.3">${title}</h3>
    <div>${items}</div>
    ${verdict ? `<div style="margin-top:16px;padding:10px 14px;background:rgba(34,197,94,.12);
      border-radius:6px;color:#86efac;font-size:14px;font-weight:600;text-align:center">${verdict}</div>` : ''}`;
  document.body.appendChild(el);
}
"""

rd.REMOVE_OVERLAYS = """
() => {
  ['valence-demo-chapter','valence-demo-explain','valence-demo-caption',
   'valence-demo-security-test','valence-demo-celebrate','valence-demo-spotlight'].forEach(id => {
    document.getElementById(id)?.remove();
  });
  document.querySelectorAll('[data-demo-highlight]').forEach(n => {
    n.style.outline = ''; n.style.outlineOffset = ''; n.removeAttribute('data-demo-highlight');
  });
}
"""

INJECT_CELEBRATE = """
(args) => {
  const [headline, sub] = args;
  document.getElementById('valence-demo-celebrate')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-celebrate';
  el.style.cssText = `
    position:fixed;inset:0;z-index:99996;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    background:rgba(3,8,12,.72);font-family:'IBM Plex Sans',system-ui,sans-serif;
  `;
  el.innerHTML = `
    <div style="text-align:center;max-width:800px;padding:48px">
      <div style="font-size:48px;margin-bottom:20px">✦</div>
      <h2 style="font-size:42px;font-weight:700;color:#fff;margin:0 0 16px;letter-spacing:-.02em;
        text-shadow:0 0 40px rgba(94,234,212,.3)">${headline}</h2>
      <p style="font-size:22px;color:#5eead4;line-height:1.5;margin:0">${sub}</p>
    </div>`;
  document.body.appendChild(el);
}
"""

rd.INTRO_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:radial-gradient(ellipse at 50% 0%,#1a4a42 0%,#0b1018 45%,#020408 100%);
    color:#e8e6e1;font-family:'IBM Plex Sans',system-ui,sans-serif;overflow:hidden}
  .wrap{max-width:1240px;text-align:center;padding:64px;position:relative;z-index:1}
  .glow{position:fixed;top:-200px;left:50%;transform:translateX(-50%);width:800px;height:400px;
    background:radial-gradient(circle,rgba(18,107,99,.25) 0%,transparent 70%);pointer-events:none}
  .mark{width:108px;height:108px;border-radius:12px;background:linear-gradient(135deg,#126B63,#0d9488);
    display:inline-flex;align-items:center;justify-content:center;font-size:52px;font-weight:700;color:#fff;
    margin-bottom:36px;box-shadow:0 20px 60px rgba(18,107,99,.4)}
  .badge-row{display:flex;justify-content:center;gap:12px;margin-bottom:28px;flex-wrap:wrap}
  .badge{padding:8px 20px;border-radius:20px;font-size:12px;letter-spacing:.14em;text-transform:uppercase}
  .badge-primary{border:1px solid rgba(94,234,212,.5);color:#5eead4}
  .badge-gold{background:rgba(252,211,77,.15);border:1px solid rgba(252,211,77,.4);color:#fcd34d}
  h1{font-size:72px;font-weight:700;letter-spacing:-.04em;margin-bottom:20px;
    background:linear-gradient(135deg,#fff 20%,#94a3b8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .sub{font-size:28px;color:#94a3b8;line-height:1.55;max-width:900px;margin:0 auto 24px;font-weight:400}
  .meta{font-size:15px;color:#64748b;margin-bottom:52px;line-height:1.8}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;text-align:left}
  .cell{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:8px;
    padding:24px;transition:all .3s}
  .cell strong{display:block;color:#5eead4;font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}
  .cell span{font-size:16px;color:#cbd5e1;line-height:1.55}
  .cell.highlight{border-color:rgba(94,234,212,.35);background:rgba(18,107,99,.12)}
</style></head><body>
<div class="glow"></div>
<div class="wrap">
  <div class="mark">V</div>
  <div class="badge-row">
    <span class="badge badge-primary">Advanced Demo · 4K Capture</span>
    <span class="badge badge-gold">Security Engineering Session</span>
  </div>
  <h1>VALENCE GRC</h1>
  <p class="sub">The platform security engineers demo when the deal matters. Every feature tested live — SIEM evidence, FAIR risk, cryptographic audit trails, enterprise ITSM.</p>
  <p class="meta">Meridian Industries Global HQ · Sandbox mode · 27 feature deep-dives · CCM tests highlighted<br>Output: advance_demo.mp4 · 3840×2160</p>
  <div class="grid">
    <div class="cell highlight"><strong>Why we win</strong><span>Live SIEM metrics become first-class compliance evidence — not checkbox attestations like Vanta or Drata.</span></div>
    <div class="cell"><strong>Board narrative</strong><span>FAIR Monte Carlo VaR and ALE in dollars. What-if simulator proves ROI before you spend.</span></div>
    <div class="cell"><strong>Enterprise grade</strong><span>ITSM sync, change mgmt, MSP console, auditor marketplace, Trust Center, Vanta migration.</span></div>
  </div>
</div></body></html>
"""

rd.OUTRO_HTML = rd.INTRO_HTML.replace(
    "<h1>VALENCE GRC</h1>",
    '<h1 style="font-size:56px">Demo Complete</h1>',
).replace(
    "<p class=\"sub\">The platform security engineers demo",
    '<p class="sub" style="color:#5eead4">Ready for enterprise pilot — every feature verified ✦</p><p class="sub">The platform security engineers demo',
).replace(
    "<p class=\"meta\">Meridian Industries",
    "<p class=\"meta\">Next: Postgres + Redis + HTTPS + SSO · ./scripts/validate_production.sh<br><br>Meridian Industries",
)

TOTAL_SECTIONS = len(DEMO_SECTIONS)
_orig_chapter = rd.chapter
_orig_explain = rd.explain
_orig_security_test = rd.security_test


def chapter(page, num, title, subtitle, bullets, duration=7.0, footer="VALENCE GRC · Advanced Demo · advance_demo.mp4", tagline=""):
    rd.clear(page)
    page.evaluate(rd.INJECT_CHAPTER, [num, str(TOTAL_SECTIONS), title, subtitle, bullets, footer, tagline])
    rd.pause(duration)
    rd.clear(page)
    rd.pause(0.5)


def explain(page, title, body, highlights, badge="How it works", duration=6.0, best_case=""):
    rd.clear(page)
    page.evaluate(rd.INJECT_EXPLAIN, [title, body, highlights, badge, best_case])
    rd.pause(duration)
    rd.clear(page)
    rd.pause(0.4)


def security_test(page, step, title, checks, duration=5.0, verdict="✓ Test passed — production ready"):
    page.evaluate(rd.INJECT_SECURITY_TEST, [step, title, checks, verdict])
    rd.pause(duration)
    page.evaluate("() => document.getElementById('valence-demo-security-test')?.remove()")
    rd.pause(0.3)


def celebrate(page, headline, sub, duration=4.5):
    page.evaluate(INJECT_CELEBRATE, [headline, sub])
    rd.pause(duration)
    page.evaluate("() => document.getElementById('valence-demo-celebrate')?.remove()")
    rd.pause(0.4)


# Patch record_demo helpers so all demo_* sections use enhanced overlays
rd.chapter = chapter
rd.explain = explain
rd.security_test = security_test


def main() -> int:
    import sys
    import urllib.request
    from playwright.sync_api import sync_playwright

    try:
        urllib.request.urlopen(BASE_URL, timeout=5)
    except Exception:
        print(f"ERROR: API not reachable at {BASE_URL}. Start ./run.sh first.", file=sys.stderr)
        return 1

    if VIDEO_TMP.exists():
        for f in VIDEO_TMP.glob("*"):
            f.unlink()
    else:
        VIDEO_TMP.mkdir(parents=True)

    print(f"[*] Recording ADVANCED demo ({RECORD_W}×{RECORD_H} → {OUTPUT_W}×{OUTPUT_H} 4K)")
    print(f"[*] Output: {OUT_MP4}")
    print("[*] Estimated runtime: 20–30 minutes.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(
            viewport={"width": RECORD_W, "height": RECORD_H},
            record_video_dir=str(VIDEO_TMP),
            record_video_size={"width": RECORD_W, "height": RECORD_H},
            color_scheme="dark",
        )
        page = context.new_page()
        page.set_content(rd.INTRO_HTML)
        pause(9.0)

        celebrate(
            page,
            "Welcome to the VALENCE Advanced Demo",
            "Every feature. Every test. Every differentiator — shown like a real enterprise sales session.",
            duration=5.0,
        )

        for i, section in enumerate(DEMO_SECTIONS, 1):
            name = section.__name__.replace("demo_", "").replace("_", " ")
            print(f"  [{i:02d}/{TOTAL_SECTIONS}] {name}…", flush=True)
            section(page)
            if i == 16:
                celebrate(
                    page,
                    "Halfway — the moat is undeniable",
                    "SIEM-native evidence · FAIR financial risk · Cryptographic audit trails",
                    duration=4.0,
                )
            elif i in (8, 24):
                celebrate(
                    page,
                    "Feature verified ✓",
                    "Tested live — exactly how security engineering runs a pre-sales demo.",
                    duration=3.0,
                )

        celebrate(
            page,
            "Every Feature. Every Test. Verified.",
            "VALENCE GRC — ready for your enterprise pilot.",
            duration=5.0,
        )

        page.set_content(rd.OUTRO_HTML)
        pause(8.0)

        video_path = Path(page.video.path())
        context.close()
        browser.close()

    print(f"[*] Upscaling to 4K and encoding {OUT_MP4.name}…", flush=True)
    convert_to_4k_mp4(video_path, OUT_MP4)
    size_mb = OUT_MP4.stat().st_size / (1024 * 1024)
    print(f"[+] Saved: {OUT_MP4}")
    print(f"    Resolution: {OUTPUT_W}×{OUTPUT_H} (4K) · Size: {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
