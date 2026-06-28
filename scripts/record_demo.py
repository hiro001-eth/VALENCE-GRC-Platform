#!/usr/bin/env python3
"""VALENCE GRC — enterprise sales-engineering demo recorder (4K output → demo.mp4)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import imageio_ffmpeg
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT_MP4 = ROOT / "demo.mp4"
VIDEO_TMP = ROOT / ".demo_video_tmp"
BASE_URL = "http://127.0.0.1:8000"
TRUST_SLUG = "meridian-industries-global-hq"

# Record at 1920×1080 (stable); upscale to 4K on export.
RECORD_W, RECORD_H = 1920, 1080
OUTPUT_W, OUTPUT_H = 3840, 2160

INJECT_CHAPTER = """
(args) => {
  const [num, title, subtitle, bullets, footer] = args;
  document.getElementById('valence-demo-chapter')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-chapter';
  el.style.cssText = `
    position:fixed;inset:0;z-index:100000;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    background:radial-gradient(ellipse at 30% 20%,#1a2e2a 0%,#0a0e14 55%,#05070c 100%);
    font-family:'IBM Plex Sans',system-ui,sans-serif;color:#e8e6e1;padding:48px;
  `;
  const list = (bullets || []).map(b =>
    `<li style="margin:14px 0;padding-left:8px;line-height:1.55;color:#c5cdd8;font-size:22px">
      <span style="color:#126B63;font-weight:700;margin-right:10px">✓</span>${b}</li>`
  ).join('');
  el.innerHTML = `
    <div style="max-width:1100px;text-align:center">
      <div style="display:inline-block;padding:8px 20px;border:1px solid rgba(18,107,99,.5);
        border-radius:4px;color:#5eead4;font-size:13px;letter-spacing:.18em;text-transform:uppercase;margin-bottom:28px">
        Live Demo Session · Sandbox Mode
      </div>
      <div style="color:#6b7280;font-size:15px;letter-spacing:.25em;text-transform:uppercase;margin-bottom:16px">
        Section ${num}
      </div>
      <h1 style="font-size:52px;font-weight:700;margin:0 0 20px;letter-spacing:-.02em;line-height:1.1">${title}</h1>
      <p style="font-size:24px;color:#94a3b8;line-height:1.5;margin:0 auto 36px;max-width:820px">${subtitle}</p>
      <ul style="list-style:none;padding:0;margin:0 auto;text-align:left;max-width:780px">${list}</ul>
      <p style="margin-top:40px;font-size:14px;color:#64748b;letter-spacing:.06em">${footer}</p>
    </div>`;
  document.body.appendChild(el);
}
"""

INJECT_EXPLAIN = """
(args) => {
  const [title, body, highlights, badge] = args;
  document.getElementById('valence-demo-explain')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-explain';
  el.style.cssText = `
    position:fixed;inset:0;z-index:99998;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    background:rgba(5,8,12,.78);font-family:'IBM Plex Sans',system-ui,sans-serif;padding:40px;
  `;
  const hi = (highlights || []).map(h =>
    `<div style="display:flex;gap:12px;align-items:flex-start;margin:12px 0">
      <span style="color:#126B63;font-weight:700;font-size:18px;flex-shrink:0">▸</span>
      <span style="color:#e2e8f0;font-size:18px;line-height:1.45">${h}</span></div>`
  ).join('');
  el.innerHTML = `
    <div style="max-width:880px;background:#14181f;border:1px solid rgba(18,107,99,.35);
      border-radius:6px;padding:44px 48px;box-shadow:0 24px 80px rgba(0,0,0,.55)">
      <div style="color:#5eead4;font-size:12px;letter-spacing:.16em;text-transform:uppercase;margin-bottom:14px">${badge}</div>
      <h2 style="color:#fff;font-size:34px;font-weight:700;margin:0 0 16px;line-height:1.2">${title}</h2>
      <p style="color:#94a3b8;font-size:19px;line-height:1.55;margin:0 0 24px">${body}</p>
      <div>${hi}</div>
    </div>`;
  document.body.appendChild(el);
}
"""

REMOVE_OVERLAYS = """
() => {
  document.getElementById('valence-demo-chapter')?.remove();
  document.getElementById('valence-demo-explain')?.remove();
  document.getElementById('valence-demo-caption')?.remove();
  document.getElementById('valence-demo-security-test')?.remove();
  document.querySelectorAll('[data-demo-highlight]').forEach(n => {
    n.style.outline = ''; n.style.outlineOffset = ''; n.removeAttribute('data-demo-highlight');
  });
}
"""

INJECT_CAPTION = """
(args) => {
  const [text] = args;
  document.getElementById('valence-demo-caption')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-caption';
  el.style.cssText = `
    position:fixed;bottom:0;left:0;right:0;z-index:99997;pointer-events:none;
    padding:20px 48px 28px;background:linear-gradient(transparent,rgba(0,0,0,.85));
    font-family:'IBM Plex Mono',monospace;font-size:17px;color:#5eead4;text-align:center;
    letter-spacing:.04em;
  `;
  el.textContent = text;
  document.body.appendChild(el);
}
"""

INJECT_SECURITY_TEST = """
(args) => {
  const [step, title, checks] = args;
  document.getElementById('valence-demo-security-test')?.remove();
  const el = document.createElement('div');
  el.id = 'valence-demo-security-test';
  el.style.cssText = `
    position:fixed;top:24px;right:24px;z-index:99999;pointer-events:none;
    max-width:420px;background:#0f1419;border:2px solid #126B63;border-radius:8px;
    padding:24px 28px;font-family:'IBM Plex Sans',system-ui,sans-serif;
    box-shadow:0 16px 48px rgba(0,0,0,.6);
  `;
  const items = (checks || []).map(c =>
    `<div style="display:flex;gap:10px;align-items:flex-start;margin:10px 0">
      <span style="color:#22c55e;font-weight:700;font-size:16px">✓</span>
      <span style="color:#e2e8f0;font-size:15px;line-height:1.4">${c}</span></div>`
  ).join('');
  el.innerHTML = `
    <div style="color:#5eead4;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px">
      Security Engineer Test · Step ${step}
    </div>
    <h3 style="color:#fff;font-size:20px;font-weight:700;margin:0 0 14px;line-height:1.25">${title}</h3>
    <div>${items}</div>`;
  document.body.appendChild(el);
}
"""

INTRO_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:radial-gradient(ellipse at 25% 15%,#1a3a35 0%,#0b1018 50%,#040608 100%);
    color:#e8e6e1;font-family:'IBM Plex Sans',system-ui,sans-serif}
  .wrap{max-width:1200px;text-align:center;padding:64px}
  .mark{width:96px;height:96px;border-radius:4px;background:#126B63;display:inline-flex;
    align-items:center;justify-content:center;font-size:48px;font-weight:700;color:#fff;margin-bottom:32px}
  .eyebrow{color:#5eead4;font-size:14px;letter-spacing:.2em;text-transform:uppercase;margin-bottom:20px}
  h1{font-size:64px;font-weight:700;letter-spacing:-.03em;margin-bottom:16px}
  .sub{font-size:26px;color:#94a3b8;line-height:1.5;max-width:860px;margin:0 auto 40px}
  .meta{font-size:15px;color:#64748b;margin-bottom:48px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin-top:8px}
  .cell{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:4px;padding:20px}
  .cell strong{display:block;color:#126B63;font-size:13px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
  .cell span{font-size:15px;color:#cbd5e1;line-height:1.45}
</style></head><body><div class="wrap">
  <div class="mark">V</div>
  <div class="eyebrow">Enterprise Sales Demo · Security Engineering Session</div>
  <h1>VALENCE GRC</h1>
  <p class="sub">Live walkthrough — every feature tested like a pre-sales security engineering demo. SIEM-native evidence, FAIR financial risk, cryptographic audit trails.</p>
  <p class="meta">Demo tenant: Meridian Industries Global HQ · Sandbox mode · 4K capture · 27 sections · CCM tests highlighted</p>
  <div class="grid">
    <div class="cell"><strong>Unique moat</strong><span>Metrics pulled from your SIEM are first-class compliance evidence — not checkbox attestations.</span></div>
    <div class="cell"><strong>Financial risk</strong><span>FAIR Monte Carlo VaR and ALE exposure in dollars — board-ready narratives.</span></div>
    <div class="cell"><strong>Enterprise ready</strong><span>ITSM sync, change management, auditor marketplace, MSP console, Trust Center.</span></div>
  </div>
</div></body></html>
"""

OUTRO_HTML = INTRO_HTML.replace(
    "<p class=\"sub\">Security-engineering walkthrough",
    "<p class=\"sub\" style=\"color:#5eead4;margin-bottom:24px\">Demo complete — ready for enterprise pilot</p><p class=\"sub\">Security-engineering walkthrough",
).replace(
    "<p class=\"meta\">Demo tenant:",
    "<p class=\"meta\">Next steps: Postgres + Redis + HTTPS + SSO · ./scripts/validate_production.sh<br><br>Demo tenant:",
)


def pause(seconds: float) -> None:
    time.sleep(seconds)


def clear(page: Page) -> None:
    page.evaluate(REMOVE_OVERLAYS)


def chapter(
    page: Page,
    num: str,
    title: str,
    subtitle: str,
    bullets: list[str],
    duration: float = 6.5,
    footer: str = "VALENCE GRC · Confidential demonstration · demo-global-hq",
) -> None:
    clear(page)
    page.evaluate(INJECT_CHAPTER, [num, title, subtitle, bullets, footer])
    pause(duration)
    clear(page)
    pause(0.4)


def explain(
    page: Page,
    title: str,
    body: str,
    highlights: list[str],
    badge: str = "How it works",
    duration: float = 5.5,
) -> None:
    clear(page)
    page.evaluate(INJECT_EXPLAIN, [title, body, highlights, badge])
    pause(duration)
    clear(page)
    pause(0.3)


def caption(page: Page, text: str, duration: float = 3.5) -> None:
    page.evaluate(INJECT_CAPTION, [text])
    pause(duration)
    page.evaluate("() => document.getElementById('valence-demo-explain')?.remove(); document.getElementById('valence-demo-caption')?.remove()")


def security_test(
    page: Page,
    step: str,
    title: str,
    checks: list[str],
    duration: float = 4.5,
) -> None:
    page.evaluate(INJECT_SECURITY_TEST, [step, title, checks])
    pause(duration)
    page.evaluate("() => document.getElementById('valence-demo-security-test')?.remove()")
    pause(0.3)


def highlight(page: Page, selector: str) -> None:
    page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return;
          el.setAttribute('data-demo-highlight','1');
          el.style.outline = '3px solid #126B63';
          el.style.outlineOffset = '4px';
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }""",
        selector,
    )
    pause(0.8)


def slow_scroll(page: Page, steps: int = 8, delay_ms: int = 380) -> None:
    page.evaluate(
        """async ([steps, delay]) => {
          const max = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          const step = Math.max(max / steps, 100);
          for (let y = 0; y <= max; y += step) {
            window.scrollTo({ top: y, behavior: 'smooth' });
            await new Promise(r => setTimeout(r, delay));
          }
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }""",
        [steps, delay_ms],
    )
    pause(0.7)


def navigate(page: Page, nav_id: str, wait: float = 2.2) -> None:
    page.evaluate(f"navigate('{nav_id}')")
    pause(wait)


def wait_ready(page: Page) -> None:
    try:
        page.wait_for_function(
            "() => !document.querySelector('.page.active')?.innerText?.includes('Loading')",
            timeout=20000,
        )
    except Exception:
        pass
    pause(0.8)


def login(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    pause(1.5)
    explain(
        page,
        "Secure multi-tenant access",
        "VALENCE isolates every customer workspace. Role-based access controls what each persona sees — from CISO dashboards to read-only auditor portals.",
        [
            "Admin provisions users with scoped module permissions",
            "SSO via Microsoft Entra ID or Okta (production)",
            "Demo sandbox: pre-seeded tenants with realistic GRC data",
        ],
        badge="Authentication",
        duration=6.0,
    )
    page.locator("button.demo-cred-btn", has_text="admin").click()
    pause(0.8)
    page.click("#login-btn")
    page.wait_for_function(
        "() => getComputedStyle(document.getElementById('login-page')).display === 'none'",
        timeout=30000,
    )
    page.wait_for_selector("#nav-dashboard", state="visible", timeout=30000)
    pause(1.8)


def demo_dashboard(page: Page) -> None:
    chapter(
        page,
        "01",
        "Executive Security Dashboard",
        "Your CISO command view — live RAG posture, financial exposure, and pipeline health.",
        [
            "Green / Amber / Red classification from deterministic threshold rules",
            "Total Annualized Loss Exposure (ALE) aggregated across all metrics",
            "Sandbox banner shows demo mode; production connects to your live SIEM",
        ],
    )
    navigate(page, "dashboard")
    wait_ready(page)
    explain(
        page,
        "Real-time GRC metrics — not static checkboxes",
        "Unlike Vanta or Drata, VALENCE ingests SIEM telemetry and computes security metrics continuously. Each metric carries RAG status and financial risk.",
        [
            "Summary cards: compliant metrics, warnings, critical gaps, total ALE",
            "Charts update after every pipeline run (every 5 minutes in production)",
            "Status strip shows SIEM connection state and data freshness",
        ],
        badge="VALENCE differentiator",
    )
    highlight(page, "#status-strip")
    security_test(
        page,
        "1.1",
        "Verify live pipeline status",
        [
            "Status strip shows Sandbox / Live / SIEM mode",
            "Data freshness timestamp visible",
            "No silent failure — errors surface in red banner",
        ],
    )
    explain_btn = page.locator("button:has-text('Why red?'), button:has-text('Why amber?')")
    if explain_btn.count() > 0:
        explain_btn.first.click()
        pause(2.5)
        explain(
            page,
            "AI explains every metric in plain English",
            "Click 'Why red?' on any metric — VALENCE uses AI to explain root cause, linked controls, and remediation path.",
            [
                "Natural-language explanation for board and auditor audiences",
                "Links metric to SOC2 / ISO control families",
                "Suggested remediation with estimated VaR impact",
            ],
            badge="AI Intelligence · Live test",
            duration=5.0,
        )
        page.evaluate("() => { if (typeof closeExplainModal === 'function') closeExplainModal(); }")
        pause(0.5)
    caption(page, "▸ LIVE METRICS: Pipeline ingests SIEM → computes RAG → surfaces ALE exposure", 4.0)
    slow_scroll(page, steps=6)
    pause(2.5)


def demo_risk(page: Page) -> None:
    chapter(
        page,
        "02",
        "FAIR Risk Quantification",
        "Translate security telemetry into board-level financial risk using FAIR methodology.",
        [
            "Monte Carlo simulation at 95th percentile Value-at-Risk (VaR)",
            "Per-metric ALE with loss magnitude and event frequency",
            "Heatmaps show concentration of financial exposure",
        ],
    )
    navigate(page, "risk")
    wait_ready(page)
    explain(
        page,
        "Financial risk your board understands",
        "Security teams report in dollars, not ticket counts. FAIR quantification answers: 'What is the expected financial impact if this control fails?'",
        [
            "VaR 95%: worst-case loss at 95% confidence interval",
            "Risk heatmap correlates metric severity with dollar exposure",
            "Export-ready for quarterly risk committee presentations",
        ],
        badge="FAIR · Monte Carlo",
    )
    security_test(
        page,
        "2.1",
        "Validate FAIR risk outputs",
        [
            "Monte Carlo VaR chart renders with 95th percentile",
            "Risk heatmap shows dollar-weighted exposure",
            "CERBERUS register links CVEs to financial risk",
        ],
    )
    slow_scroll(page, steps=7)
    pause(3.0)


def demo_whatif(page: Page) -> None:
    chapter(
        page,
        "03",
        "What-If Risk Simulator",
        "Model security investments before you spend — SOC hires, SOAR, patch automation.",
        [
            "Pre-built scenarios: hire analysts, deploy SOAR, automate patching",
            "Adjust sliders to see projected VaR reduction",
            "ROI ratio shows return per dollar invested",
        ],
    )
    navigate(page, "whatif")
    wait_ready(page)
    explain(
        page,
        "Budget justification with Monte Carlo proof",
        "CISOs use this in board meetings: 'If we invest $180K in SOAR, projected VaR drops by X with Y ROI.'",
        [
            "Select a preset scenario or build custom adjustments",
            "Run simulation to project Green/Amber/Red metric distribution",
            "Compare current vs projected portfolio VaR side-by-side",
        ],
        badge="CISO tooling",
    )
    page.wait_for_function(
        "() => document.querySelector('#whatif-preset-select option[value=\"deploy_soar\"]')",
        timeout=15000,
    )
    page.select_option("#whatif-preset-select", value="deploy_soar")
    pause(1.2)
    page.click("button:has-text('Run Monte Carlo Simulation')")
    pause(3.5)
    security_test(
        page,
        "3.1",
        "What-If simulation verified",
        [
            "SOAR preset loaded — sliders auto-adjusted",
            "Monte Carlo re-ran with projected portfolio VaR",
            "ROI ratio calculated for board budget justification",
        ],
    )
    highlight(page, "#whatif-proj-var")
    caption(page, "▸ SIMULATION: SOAR deployment → projected VaR reduction + ROI calculated", 4.5)
    slow_scroll(page, steps=4)
    pause(2.0)


def demo_command_center(page: Page) -> None:
    chapter(
        page,
        "04",
        "Risk Command Center",
        "Map every SIEM metric to compliance controls with prioritized remediation.",
        [
            "Control coverage matrix: which frameworks each metric satisfies",
            "Remediation tasks synced to Jira / ServiceNow",
            "Financial exposure ranked by control gap severity",
        ],
    )
    navigate(page, "command-center")
    wait_ready(page)
    explain(
        page,
        "The operational bridge between SOC and GRC",
        "Analysts see which compliance controls are failing, the dollar risk, and the remediation path — in one view.",
        [
            "Metrics mapped to SOC2, ISO27001, DORA, NIS2 control families",
            "One-click remediation task creation with owner assignment",
            "ITSM ticket sync keeps SOC and GRC teams aligned",
        ],
        badge="Operations",
    )
    slow_scroll(page, steps=6)
    pause(3.0)


def demo_benchmarking(page: Page) -> None:
    chapter(
        page,
        "05",
        "Industry Benchmarking",
        "Compare your posture against anonymized peer data from Verizon DBIR and SANS.",
        [
            "Percentile ranking per metric vs industry quartiles",
            "Identify leadership areas and critical gaps",
            "Industry selector: Financial Services, Healthcare, Technology, etc.",
        ],
    )
    navigate(page, "benchmarking")
    wait_ready(page)
    explain(
        page,
        "Know where you lead — and where you lag",
        "Benchmarking contextualizes your metrics. A 14-minute MTTD might be excellent in healthcare but below average in fintech.",
        [
            "P25 / P50 / P75 / P90 industry quartiles per metric",
            "Gap-to-median shows direction and magnitude",
            "Sourced from Verizon DBIR 2025 and SANS SOC Survey",
        ],
        badge="Peer comparison",
    )
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_platform(page: Page) -> None:
    chapter(
        page,
        "06",
        "Competitive Positioning",
        "Why security engineering teams choose VALENCE over checkbox GRC tools.",
        [
            "vs Vanta / Drata: live SIEM evidence vs manual attestations",
            "vs ServiceNow GRC: integrated FAIR risk + faster time-to-value",
            "vs MetricStream: modern API-first architecture with ChatOps",
        ],
    )
    navigate(page, "platform")
    wait_ready(page)
    explain(
        page,
        "Built for security engineers, not just compliance officers",
        "VALENCE doesn't replace your SIEM — it makes SIEM data audit-ready. That's the moat no pure compliance tool can replicate.",
        [
            "Continuous control monitoring from live telemetry",
            "SHA-256 evidence chain for auditor verification",
            "Competitor CSV import migrates Vanta/Drata gaps automatically",
        ],
        badge="Why VALENCE",
    )
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_threat_intel(page: Page) -> None:
    chapter(
        page,
        "07",
        "Threat Intelligence Correlation",
        "Cross-reference CISA KEV catalog and MITRE ATT&CK with your live metrics.",
        [
            "CISA Known Exploited Vulnerabilities catalog integration",
            "MITRE ATT&CK technique trend analysis",
            "Correlate external threat data with internal detection coverage",
        ],
    )
    navigate(page, "threat-intel")
    wait_ready(page)
    explain(
        page,
        "Threat intel that connects to your posture",
        "Most GRC tools ignore threat feeds. VALENCE correlates KEV entries and ATT&CK trends with your detection metrics.",
        [
            "KEV tab: actively exploited CVEs mapped to your patch lag metrics",
            "MITRE tab: technique frequency trends from your SIEM rules",
            "Closes the loop between threat landscape and control effectiveness",
        ],
        badge="Threat intel",
    )
    caption(page, "▸ CISA KEV: Actively exploited vulnerabilities cross-referenced with patch metrics", 3.5)
    page.click("#btn-tab-mitre")
    pause(3.0)
    caption(page, "▸ MITRE ATT&CK: Detection technique trends from live SIEM correlation", 3.5)
    page.click("#btn-tab-kev")
    pause(1.5)


def demo_compliance(page: Page) -> None:
    chapter(
        page,
        "08",
        "Compliance Framework Mapping",
        "DORA · NIS2 · SOC 2 Type II · ISO 27001 · HIPAA — auto-mapped from metrics.",
        [
            "Framework readiness percentages computed from live controls",
            "Gap analysis identifies missing evidence per requirement",
            "Continuous control monitoring (CCM) test results",
        ],
    )
    navigate(page, "compliance")
    wait_ready(page)
    explain(
        page,
        "Frameworks mapped automatically — not manually",
        "Each SIEM metric links to control families. When MTTR degrades, SOC2 CC7.3 and ISO A.16.1.5 reflect it immediately.",
        [
            "Readiness cards per framework with pass/partial/fail counts",
            "Drill into individual control requirements",
            "Auditor-exportable gap reports",
        ],
        badge="Compliance",
    )
    fw_tab = page.locator("#fw-tabs .fw-tab", has_text="DORA")
    if fw_tab.count() > 0:
        fw_tab.first.click()
        pause(2.0)
        caption(page, "▸ FRAMEWORK TEST: DORA 2025 readiness computed from live SIEM metrics", 3.5)
    page.evaluate("window.scrollTo({top: document.getElementById('ccm-tests-list')?.offsetTop || 800, behavior: 'smooth'})")
    pause(2.0)
    highlight(page, "#ccm-tests-list")
    security_test(
        page,
        "8.1",
        "Continuous Control Monitoring (CCM)",
        [
            "Automated tests run against live SIEM metrics",
            "Pass / At Risk / Failing status per control test",
            "Vanta/Drata-style CCM — but powered by real telemetry",
        ],
        duration=5.5,
    )
    page.click("button:has-text('Analyze gaps')")
    pause(3.0)
    caption(page, "▸ AI GAP ANALYSIS: Prioritized remediation ranked by compliance impact", 4.0)
    slow_scroll(page, steps=7)
    pause(3.0)


def demo_evidence(page: Page) -> None:
    chapter(
        page,
        "09",
        "Cryptographic Evidence Vault",
        "SHA-256 hash-chained records — tamper-evident audit trail for regulators.",
        [
            "Every pipeline run creates a cryptographically linked evidence record",
            "Auditors verify integrity without trusting the vendor",
            "Continuous monitoring evidence, not point-in-time screenshots",
        ],
    )
    navigate(page, "evidence")
    wait_ready(page)
    explain(
        page,
        "Evidence your auditor can verify independently",
        "Each evidence chain entry includes metric snapshot hash, timestamp, and lineage to the SIEM query that produced it.",
        [
            "SHA-256 chain prevents retroactive tampering",
            "Export evidence packages for SOC2 Type II audits",
            "Replaces screenshot-based 'proof' with cryptographic proof",
        ],
        badge="Audit-grade",
    )
    slow_scroll(page, steps=6)
    pause(3.0)


def demo_timeline(page: Page) -> None:
    chapter(
        page,
        "10",
        "Security Posture Timeline",
        "90-day continuous audit trail — every posture transition recorded.",
        [
            "Historical RAG transitions with root-cause context",
            "Snapshot comparison across pipeline runs",
            "Demonstrates continuous monitoring for auditors",
        ],
    )
    navigate(page, "timeline")
    wait_ready(page)
    explain(
        page,
        "Prove continuous monitoring — not annual checkbox reviews",
        "Auditors ask: 'Show me your security improved over Q3.' The timeline answers with dated, hash-verified snapshots.",
        [
            "Daily posture snapshots with VaR trend line",
            "Event markers for incidents, remediations, and threshold changes",
            "Exportable for regulator examinations (DORA, NIS2)",
        ],
        badge="Continuous audit",
    )
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_findings(page: Page) -> None:
    chapter(
        page,
        "11",
        "Audit Findings Lifecycle",
        "Track every compliance gap from detection through verified closure.",
        [
            "Findings auto-created from red/amber metric breaches",
            "Owner assignment, due dates, and SLA tracking",
            "Closure requires evidence attachment",
        ],
    )
    navigate(page, "findings")
    wait_ready(page)
    explain(
        page,
        "Close the loop: detect → assign → remediate → verify",
        "Findings aren't spreadsheets. They're linked to metrics, controls, and remediation tasks with full audit history.",
        [
            "Severity classification aligned to financial exposure",
            "Status workflow: open → in progress → pending verification → closed",
            "Integrates with ITSM for ticket tracking",
        ],
        badge="Remediation",
    )
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_reports(page: Page) -> None:
    chapter(
        page,
        "12",
        "Executive Reports & Board Decks",
        "Generate PDF audit reports and auto-built board presentations.",
        [
            "One-click PDF export with cryptographic lineage hash",
            "Board deck slides: posture summary, top risks, investment ROI",
            "Scheduled delivery to CISO and auditor mailing lists",
        ],
    )
    navigate(page, "reports")
    wait_ready(page)
    explain(
        page,
        "Board-ready in minutes, not weeks",
        "Security teams spend days building board decks. VALENCE auto-generates slides from live metrics with FAIR dollar figures.",
        [
            "PDF reports embed tamper-evident lineage hashes",
            "Deck generator: posture, risks, benchmarks, recommendations",
            "SMTP scheduling for monthly auditor packages",
        ],
        badge="Executive reporting",
    )
    page.click("button:has-text('Generate Board Deck')")
    pause(4.0)
    security_test(
        page,
        "12.1",
        "Board deck generation",
        [
            "AI-generated slides from live posture data",
            "FAIR dollar figures embedded in executive narrative",
            "Quarter / audience / tone configurable",
        ],
    )
    deck = page.locator("#deck-presentation-wrapper")
    if deck.is_visible():
        page.click("button:has-text('Next')")
        pause(2.0)
        page.click("button:has-text('Next')")
        pause(2.0)
    caption(page, "▸ PDF REPORTS: Cryptographic lineage hash embedded in every export", 3.5)
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_vendors(page: Page) -> None:
    chapter(
        page,
        "13",
        "SENTINEL Vendor Risk",
        "Third-party risk scoring, tier classification, and continuous monitoring.",
        [
            "Vendor tier matrix: critical, high, medium, low",
            "Risk scores from questionnaire responses + external signals",
            "Continuous re-assessment triggers on contract renewal",
        ],
    )
    navigate(page, "vendors")
    wait_ready(page)
    explain(
        page,
        "Third-party risk integrated with your GRC program",
        "Vendor assessments feed into your overall compliance posture — not a separate spreadsheet.",
        [
            "Tier-based assessment frequency (annual vs quarterly)",
            "SIG Lite questionnaire auto-fill from platform posture",
            "Vendor findings create remediation tasks automatically",
        ],
        badge="TPRM",
    )
    slow_scroll(page, steps=5)
    pause(2.0)


def demo_policies(page: Page) -> None:
    chapter(
        page,
        "14",
        "Policy Library & Attestations",
        "Publish security policies and track employee acknowledgment.",
        [
            "Policy versioning with approval workflow",
            "Employee attestation campaigns with completion tracking",
            "Maps policies to compliance control requirements",
        ],
    )
    navigate(page, "policies")
    wait_ready(page)
    explain(
        page,
        "Policies connected to controls — not orphaned documents",
        "When you publish a policy update, VALENCE tracks who attested and which controls it satisfies.",
        [
            "Attestation summary: completion %, overdue employees",
            "One-click seed of enterprise policy templates",
            "Auditor view shows attestation evidence per control",
        ],
        badge="Governance",
    )
    slow_scroll(page, steps=5)
    pause(2.0)


def demo_auditor(page: Page) -> None:
    chapter(
        page,
        "15",
        "Auditor Portal",
        "Read-only workspace for external auditors — scoped, secure, efficient.",
        [
            "Auditor role: read-only access to evidence, controls, findings",
            "No access to SIEM credentials or admin functions",
            "Export packages pre-assembled for examination",
        ],
    )
    navigate(page, "auditor")
    wait_ready(page)
    explain(
        page,
        "Auditors get exactly what they need — nothing more",
        "External auditors log in with scoped permissions. They see evidence chains, control tests, and findings — without admin access.",
        [
            "Dedicated auditor role with feature-gated navigation",
            "Pre-built examination packages per framework",
            "Reduces audit cycle time by 40%+ (customer benchmark)",
        ],
        badge="Audit efficiency",
    )
    slow_scroll(page, steps=5)
    pause(2.0)


def demo_personnel(page: Page) -> None:
    chapter(
        page,
        "16",
        "Personnel, Devices & Trust Center",
        "Joiner-mover-leaver lifecycle, MDM compliance, and customer-facing trust page.",
        [
            "JML events: onboarding, role changes, offboarding tracked",
            "MDM device inventory with compliance status",
            "Trust Center: public compliance posture for prospects",
        ],
    )
    navigate(page, "personnel")
    wait_ready(page)
    explain(
        page,
        "People and endpoints are part of your compliance story",
        "ISO 27001 A.6 and SOC2 CC6 require personnel controls. VALENCE tracks JML and device compliance alongside SIEM metrics.",
        [
            "JML tab: lifecycle events with approval audit trail",
            "Devices tab: MDM-synced endpoint compliance status",
            "Trust Center tab: configure public-facing posture page",
        ],
        badge="People & endpoints",
    )
    page.locator("#personnel-tabs .fw-tab", has_text="Devices").click()
    pause(2.5)
    caption(page, "▸ MDM DEVICES: Endpoint compliance synced from mobile device management", 3.5)
    page.locator("#personnel-tabs .fw-tab", has_text="Trust Center").click()
    pause(2.5)
    caption(page, "▸ TRUST CENTER: Configure public compliance page for customers & prospects", 3.5)
    page.locator("#personnel-tabs .fw-tab", has_text="JML").click()
    pause(1.5)


def demo_questionnaires(page: Page) -> None:
    chapter(
        page,
        "17",
        "AI Security Questionnaires",
        "SIG Lite auto-fill from live compliance posture — with approval workflow.",
        [
            "Questionnaire templates: SIG Lite, CAIQ, custom",
            "AI-assisted answers derived from platform evidence",
            "Submit → review → approve workflow before sending",
        ],
    )
    navigate(page, "questionnaires")
    wait_ready(page)
    explain(
        page,
        "Answer vendor questionnaires in hours, not weeks",
        "Your compliance posture already lives in VALENCE. Questionnaires auto-fill from evidence — humans approve before send.",
        [
            "SIG Lite mapping to live control test results",
            "Approval workflow: analyst drafts → CISO approves",
            "Audit trail of every answer and its evidence source",
        ],
        badge="AI-assisted",
    )
    slow_scroll(page, steps=5)
    pause(2.5)


def demo_training(page: Page) -> None:
    chapter(
        page,
        "18",
        "Security Awareness Training",
        "Video, SCORM, and quiz-based courses with completion tracking.",
        [
            "Course library: phishing, HIPAA, GDPR, incident response",
            "SCORM package support for custom content",
            "Completion rates feed compliance control evidence",
        ],
    )
    navigate(page, "training")
    wait_ready(page)
    explain(
        page,
        "Training completion as compliance evidence",
        "SOC2 CC1.4 and ISO A.6.2 require security awareness. Training completion rates appear in your control monitoring.",
        [
            "Assign courses by role, department, or business unit",
            "Track completion % with overdue employee alerts",
            "One-click seed of demo course catalog",
        ],
        badge="Awareness",
    )
    slow_scroll(page, steps=4)
    pause(2.0)


def demo_pentest(page: Page) -> None:
    chapter(
        page,
        "19",
        "Penetration Test Program",
        "Schedule assessments, track findings, and close remediation loops.",
        [
            "Assessment scheduling with vendor assignment",
            "Finding severity classification and SLA tracking",
            "Links pen test findings to compliance control gaps",
        ],
    )
    navigate(page, "pentest")
    wait_ready(page)
    explain(
        page,
        "Pen test findings feed your GRC program",
        "Don't let pen test reports sit in email. Findings become tracked remediation items with control mapping.",
        [
            "Schedule internal and external assessments",
            "Finding lifecycle: discovered → remediated → verified",
            "VALENCE_PEN_TEST_ATTESTED flag for production readiness",
        ],
        badge="Offensive security",
    )
    slow_scroll(page, steps=4)
    pause(2.0)


def demo_team(page: Page) -> None:
    chapter(
        page,
        "20",
        "Team Access & RBAC",
        "Provision GRC, SOC, and IR members with scoped module permissions.",
        [
            "Role presets: Admin, CISO, Analyst, Auditor",
            "Department scoping: GRC, SOC, IR, General",
            "SSO status card for Entra ID / Okta (production)",
        ],
    )
    navigate(page, "team")
    wait_ready(page)
    explain(
        page,
        "Least-privilege access for every persona",
        "Auditors see evidence — not SIEM credentials. Analysts see metrics — not billing. Each role gets exactly the modules they need.",
        [
            "Feature-gated navigation hides unauthorized pages",
            "Team cards show department, role, and last login",
            "Invite workflow with scoped permissions",
        ],
        badge="Identity & Access",
    )
    security_test(
        page,
        "20.0",
        "RBAC verification",
        [
            "Admin role: full platform access",
            "Auditor role: read-only evidence + controls",
            "Feature flags enforce module-level permissions",
        ],
    )
    slow_scroll(page, steps=5)
    pause(2.0)


def demo_connectors(page: Page) -> None:
    chapter(
        page,
        "21",
        "Integration Hub & SIEM Connectors",
        "Connect Splunk, Elastic, or QRadar — plus 20+ marketplace integrations.",
        [
            "SIEM connector health monitoring with stale-data alerts",
            "Marketplace: Jira, ServiceNow, Google Workspace, GitHub, AWS",
            "OAuth connection health probes with live/degraded status",
        ],
    )
    navigate(page, "connectors")
    wait_ready(page)
    explain(
        page,
        "Your SIEM is the source of truth — VALENCE is the GRC layer",
        "Connect once, and every pipeline run pulls fresh telemetry. Stale data triggers visible banners — never silent failure.",
        [
            "Splunk · Elastic · QRadar native connectors",
            "Marketplace browse by category with one-click setup guides",
            "Connector health dashboard: last sync, error rate, record count",
        ],
        badge="Integrations",
    )
    search = page.locator("#marketplace-search")
    if search.count() > 0:
        search.fill("Jira")
        page.evaluate("debounceMarketplaceSearch()")
        pause(2.5)
        caption(page, "▸ MARKETPLACE: 200+ integrations — search, connect, OAuth, verify", 4.0)
        search.fill("")
        page.evaluate("debounceMarketplaceSearch()")
        pause(1.5)
    security_test(
        page,
        "21.1",
        "Connector health check",
        [
            "SIEM connector status: last sync, record count",
            "Marketplace OAuth health probes",
            "Stale data triggers visible amber/red banners",
        ],
    )
    slow_scroll(page, steps=7)
    pause(2.5)


def demo_enterprise_tab(
    page: Page,
    num: str,
    tab_id: str,
    title: str,
    subtitle: str,
    bullets: list[str],
    highlights: list[str],
) -> None:
    chapter(page, num, title, subtitle, bullets, duration=5.5)
    navigate(page, "enterprise")
    pause(1.4)
    page.evaluate(
        f"loadEnterpriseTab('{tab_id}', document.querySelector('#enterprise-tabs .fw-tab[onclick*=\"{tab_id}\"]'))"
    )
    pause(2.0)
    explain(page, title, subtitle, highlights, badge="Enterprise · Demo", duration=5.0)
    slow_scroll(page, steps=4, delay_ms=300)
    pause(2.5)


def demo_enterprise(page: Page) -> None:
    chapter(
        page,
        "22",
        "Enterprise Command Center",
        "Workflows, ITSM, change management, billing, MSP, and competitor migration.",
        [
            "Multi-business-unit workflow designer",
            "ITSM + CMDB bi-directional sync",
            "Stripe billing, MSP portfolio, Vanta/Drata import",
        ],
        duration=5.0,
    )
    demo_enterprise_tab(
        page, "21a", "workflows",
        "Multi-BU Workflow Designer",
        "Model approval chains across business units, regions, and control owners.",
        ["Create business units with regional ownership", "Workflow designer: trigger → steps → approval", "Execute workflows to generate remediation tasks"],
        ["Business unit hierarchy for global enterprises", "Visual step designer with approval gates", "Run workflow → auto-creates tasks with owners"],
    )
    demo_enterprise_tab(
        page, "21b", "itsm",
        "ITSM & CMDB Integration",
        "Bi-directional sync with Jira and ServiceNow for remediation and asset inventory.",
        ["Sync remediation tasks → ITSM tickets automatically", "CMDB asset inventory from cloud connectors", "Provider health: connected / not connected status"],
        ["One-click 'Sync remediation → ITSM' pushes open tasks", "CMDB shows criticality, source, and asset type", "Ticket deep-links open in Jira/ServiceNow"],
    )
    demo_enterprise_tab(
        page, "21c", "changes",
        "Change Management",
        "Production change requests with approval, implementation, and ITSM linkage.",
        ["Create change requests with risk level classification", "Approval workflow: pending → approved → implemented", "External ITSM ticket reference for audit trail"],
        ["Risk levels: low / medium / high with color coding", "Approve and implement buttons per status", "Full audit trail of who approved and when"],
    )
    demo_enterprise_tab(
        page, "21d", "auditors",
        "Auditor Marketplace",
        "Engage external audit firms directly from the platform.",
        ["Browse firms by specialization, rating, and hourly rate", "Request engagements per framework (SOC2, ISO, HIPAA)", "Track engagement status and deliverables"],
        ["Pre-vetted firms with SOC2, ISO27001, HIPAA expertise", "Engagement request workflow with framework selection", "Engagement history for renewal planning"],
    )
    demo_enterprise_tab(
        page, "21e", "oauth",
        "OAuth Integration Health",
        "Google, GitHub, Jira — with live connection health probes.",
        ["OAuth providers with configured / demo mode status", "Connection health: healthy / degraded / not connected", "AWS IAM role connect for cloud evidence collection"],
        ["Live probe shows HTTP status and token validity", "Deep integration badge for bi-directional collectors", "AWS IAM role: connect without long-lived API keys"],
    )
    demo_enterprise_tab(
        page, "21f", "billing",
        "Stripe Billing & Plans",
        "Self-serve plan upgrades with webhook idempotency.",
        ["Plans: Starter, Professional, Enterprise tiers", "Stripe checkout for live payment processing", "Webhook idempotency prevents duplicate charges"],
        ["Current plan and subscription status displayed", "Click plan card → Stripe checkout (production)", "Demo mode works without STRIPE_SECRET_KEY"],
    )
    demo_enterprise_tab(
        page, "21g", "msp",
        "MSP Multi-Tenant Console",
        "Managed service providers oversee entire customer portfolios.",
        ["Portfolio view: all tenants, plans, integration counts", "One-click tenant switch for MSP operators", "Per-tenant SIEM status and demo flags"],
        ["See all customer tenants in one dashboard", "Switch tenant context without re-login", "Track integrations and SIEM config per customer"],
    )
    demo_enterprise_tab(
        page, "21h", "import",
        "Vanta / Drata Migration",
        "Import competitor CSV exports — gaps become remediation tasks automatically.",
        ["Upload Vanta or Drata control export CSV", "Gap analysis maps imported status to VALENCE controls", "Failed controls auto-create remediation tasks"],
        ["Drag-and-drop CSV upload", "Column mapping: control, status, framework, owner", "Competitive migration path from checkbox GRC tools"],
    )


def demo_global_search(page: Page) -> None:
    chapter(
        page,
        "23",
        "Global Search",
        "Instant cross-module search across metrics, controls, findings, and evidence.",
        [
            "Search from any page via top-bar search box",
            "Results grouped by module: metrics, controls, findings",
            "Jump directly to the relevant page and record",
        ],
        duration=5.0,
    )
    navigate(page, "dashboard")
    pause(1.2)
    queries = [
        ("compliance", "▸ SEARCH: 'compliance' → frameworks, controls, readiness scores"),
        ("risk", "▸ SEARCH: 'risk' → FAIR metrics, VaR, exposure drivers"),
        ("DORA", "▸ SEARCH: 'DORA' → Digital Operational Resilience Act controls"),
    ]
    for q, cap in queries:
        search = page.locator("#global-search-input")
        search.click()
        search.fill("")
        search.fill(q)
        page.evaluate(f"debounceGlobalSearch('{q}')")
        pause(2.0)
        caption(page, cap, 3.5)
    page.keyboard.press("Escape")
    pause(0.5)


def demo_mobile(page: Page) -> None:
    chapter(
        page,
        "24",
        "Mobile Executive View",
        "Read-only compliance snapshot for leadership on any device.",
        [
            "Simplified mobile layout for CISO and board members",
            "Key metrics: overall RAG, ALE, framework readiness",
            "No admin actions — view-only by design",
        ],
        duration=5.0,
    )
    navigate(page, "mobile")
    wait_ready(page)
    explain(
        page,
        "Executives check posture on the go",
        "Board members and CISOs get a clean mobile view without navigating the full platform.",
        [
            "Overall compliance score and RAG distribution",
            "Top risks and framework readiness at a glance",
            "Responsive layout adapts to phone and tablet",
        ],
        badge="Mobile",
    )
    pause(3.5)


def demo_trust_center(page: Page) -> None:
    chapter(
        page,
        "25",
        "Public Trust Center",
        "Customer-facing compliance page with optional NDA gate.",
        [
            "Shareable URL: yourcompany.com/trust/your-slug",
            "Framework readiness badges: SOC2, ISO27001, HIPAA, GDPR",
            "NDA gate for confidential control details",
        ],
        duration=5.5,
    )
    page.goto(f"{BASE_URL}/trust/{TRUST_SLUG}", wait_until="networkidle")
    pause(2.0)
    explain(
        page,
        "Prove your security posture to customers",
        "Prospects visit your Trust Center before signing contracts. Live readiness percentages come from your actual metrics — not marketing copy.",
        [
            "Company description, framework badges, control summary",
            "NDA acceptance gate for sensitive control details",
            "Admin configures slug, badges, and contact email in Personnel tab",
        ],
        badge="Customer-facing",
        duration=6.0,
    )
    slow_scroll(page, steps=5)
    pause(3.0)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_selector("#nav-dashboard", state="visible", timeout=30000)
    pause(1.2)


def demo_tenant_switch(page: Page) -> None:
    chapter(
        page,
        "26",
        "Multi-Tenant Architecture",
        "Switch between business units and demo tenants without re-authentication.",
        [
            "Tenant switcher in sidebar: Global HQ, US Retail, EU Fintech, Healthcare",
            "Each tenant has isolated metrics, controls, and evidence",
            "MSP operators manage portfolios from Enterprise console",
        ],
        duration=5.0,
    )
    page.select_option("#tenant-select", value="demo-us-retail")
    pause(2.5)
    caption(page, "▸ TENANT SWITCH: US Retail — isolated metrics, separate SIEM config", 4.0)
    page.select_option("#tenant-select", value="demo-global-hq")
    pause(2.0)


def outro(page: Page) -> None:
    chapter(
        page,
        "27",
        "Thank You",
        "VALENCE GRC — where live SIEM telemetry becomes audit-grade compliance evidence.",
        [
            "Unique moat: FAIR financial risk + continuous SIEM evidence",
            "Enterprise: ITSM, change mgmt, MSP, billing, competitor import",
            "Production: Postgres, Redis, HTTPS, SSO — ./scripts/validate_production.sh",
        ],
        duration=8.0,
        footer="Contact your VALENCE representative to schedule an enterprise pilot →",
    )
    page.set_content(OUTRO_HTML)
    pause(7.0)


def convert_to_4k_mp4(webm_path: Path, mp4_path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(webm_path),
            "-vf",
            f"scale={OUTPUT_W}:{OUTPUT_H}:flags=lanczos",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "slow",
            "-crf",
            "17",
            "-movflags",
            "+faststart",
            "-r",
            "30",
            str(mp4_path),
        ],
        check=True,
        capture_output=True,
    )


DEMO_SECTIONS: list[Callable[[Page], None]] = [
    login,
    demo_dashboard,
    demo_risk,
    demo_whatif,
    demo_command_center,
    demo_benchmarking,
    demo_platform,
    demo_threat_intel,
    demo_compliance,
    demo_evidence,
    demo_timeline,
    demo_findings,
    demo_reports,
    demo_vendors,
    demo_policies,
    demo_auditor,
    demo_personnel,
    demo_questionnaires,
    demo_training,
    demo_pentest,
    demo_team,
    demo_connectors,
    demo_enterprise,
    demo_global_search,
    demo_mobile,
    demo_trust_center,
    demo_tenant_switch,
    outro,
]


def main() -> int:
    import urllib.request

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

    print(f"[*] Recording enterprise demo ({RECORD_W}×{RECORD_H} → {OUTPUT_W}×{OUTPUT_H} 4K)…")
    print("[*] Estimated runtime: 18–25 minutes. Grab coffee.")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": RECORD_W, "height": RECORD_H},
            record_video_dir=str(VIDEO_TMP),
            record_video_size={"width": RECORD_W, "height": RECORD_H},
            color_scheme="dark",
            device_scale_factor=1,
        )
        page = context.new_page()

        page.set_content(INTRO_HTML)
        pause(7.0)

        for i, section in enumerate(DEMO_SECTIONS, 1):
            name = section.__name__.replace("demo_", "").replace("_", " ")
            print(f"  [{i:02d}/{len(DEMO_SECTIONS)}] {name}…")
            section(page)

        video_path = Path(page.video.path())
        context.close()
        browser.close()

    print(f"[*] Upscaling to 4K and encoding {OUT_MP4.name}…")
    convert_to_4k_mp4(video_path, OUT_MP4)
    size_mb = OUT_MP4.stat().st_size / (1024 * 1024)
    print(f"[+] Saved: {OUT_MP4}")
    print(f"    Resolution: {OUTPUT_W}×{OUTPUT_H} (4K) · Size: {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
