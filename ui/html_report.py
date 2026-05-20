"""HTML report generation for NGS Sample QC LIMS.

Output structure:
    {output_dir}/
    ├── index.html
    └── assets/
        ├── {sample_id}_electro.png
        └── ...
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Status styling ────────────────────────────────────────────────────────────
_ST_BG  = {"Pass": "#E8F5E9", "Warning": "#FFF8E1", "Fail": "#FFEBEE",
            "Pending": "#F5F5F5", "No Data": "#F5F5F5"}
_ST_FG  = {"Pass": "#2E7D32", "Warning": "#BF360C", "Fail": "#B71C1C",
            "Pending": "#757575", "No Data": "#757575"}


def _badge(status: str) -> str:
    bg = _ST_BG.get(status, "#F5F5F5")
    fg = _ST_FG.get(status, "#555")
    return (f'<span style="background:{bg};color:{fg};padding:2px 10px;'
            f'border-radius:10px;font-weight:700;font-size:0.82em;'
            f'white-space:nowrap">{status or "—"}</span>')


def _fmt(val, decimals: int = 2) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return str(val)


def _td(val, bold: bool = False, color: str = "") -> str:
    style = ""
    if bold:
        style += "font-weight:700;"
    if color:
        style += f"color:{color};"
    content = val if val is not None else "—"
    s = f' style="{style}"' if style else ""
    return f"<td{s}>{content}</td>"


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 13px; color: #1a1a2e; background: #f0f2f5;
    padding: 28px 20px;
}
.report-wrap { max-width: 1080px; margin: 0 auto; }

/* ── Cover ── */
.cover {
    background: white; border-radius: 10px; padding: 40px 48px 32px;
    margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.10);
}
.cover h1 { font-size: 2em; color: #1A237E; margin-bottom: 4px; }
.cover .subtitle { color: #666; font-size: 0.92em; margin-bottom: 20px; }
.batch-stats { display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0 20px; }
.batch-stats .stat {
    padding: 8px 18px; border-radius: 8px; font-weight: 700;
    font-size: 0.95em; border: 1.5px solid transparent;
}

/* ── Section card ── */
.card {
    background: white; border-radius: 10px; padding: 28px 32px;
    margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.09);
    page-break-inside: avoid;
}
.card + .sample-section { page-break-before: always; }
.section-title {
    font-size: 1.05em; font-weight: 700; color: #1A237E;
    margin-bottom: 14px; padding-bottom: 6px;
    border-bottom: 2px solid #E3E8F4;
    display: flex; align-items: center; gap: 8px;
}
.section-title .icon { font-size: 1.1em; }

/* ── Sample header ── */
.sample-card {
    background: white; border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,.09);
    margin-bottom: 20px; overflow: hidden;
    page-break-before: always;
}
.sample-card:first-of-type { page-break-before: auto; }
.sample-hdr {
    background: linear-gradient(135deg, #1A237E 0%, #283593 100%);
    color: white; padding: 18px 28px 14px;
    display: flex; justify-content: space-between; align-items: flex-start;
}
.sample-title { font-size: 1.25em; font-weight: 700; margin-bottom: 4px; }
.sample-meta { font-size: 0.83em; opacity: 0.85; }
.status-pill {
    padding: 5px 16px; border-radius: 20px; font-weight: 700;
    font-size: 0.9em; white-space: nowrap; border: 2px solid rgba(255,255,255,.6);
}
.sample-body { padding: 20px 28px 24px; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; font-size: 0.88em; }
thead th {
    background: #2C3E6B; color: white; padding: 8px 10px;
    text-align: center; font-weight: 600; white-space: pre-line;
    border: 1px solid #1A237E;
}
tbody td {
    padding: 6px 10px; border: 1px solid #E4E8F0;
    text-align: center; vertical-align: middle;
}
tbody tr:nth-child(even) td { background: #F4F7FB; }
tbody tr:hover td { background: #EBF1FF; }
.col-left { text-align: left !important; }
.col-step { font-weight: 600; color: #2C3E6B; text-align: left !important; }

/* ── Electropherogram ── */
.electro-wrap { text-align: center; margin: 8px 0; }
.electro-wrap img {
    max-width: 100%; max-height: 380px; border-radius: 6px;
    border: 1px solid #DDE3EF; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}

/* ── Criteria note ── */
.criteria { font-size: 0.78em; color: #888; font-style: italic; margin-top: 6px; }

/* ── TOC ── */
.toc { columns: 2; column-gap: 24px; }
.toc a {
    display: block; padding: 3px 0; color: #1A237E;
    text-decoration: none; font-size: 0.9em;
    border-bottom: 1px dotted #DDE3EF; margin-bottom: 2px;
}
.toc a:hover { color: #3949AB; }

@media print {
    body { background: white; padding: 0; }
    .sample-card { page-break-before: always; box-shadow: none; }
    .card { box-shadow: none; }
}
"""


# ── Electropherogram image ────────────────────────────────────────────────────
def _save_electro_png(sid: str, assets_dir: Path) -> Optional[str]:
    """Render electropherogram and save as PNG. Returns relative path or None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from analysis.visualizer import load_electropherogram_traces, qc_visualizer

        traces, calibration = load_electropherogram_traces(sid)
        if not traces:
            return None
        fig, _, _, _, _ = qc_visualizer.plot_electropherogram_overlay(
            sid, traces, calibration
        )
        if fig is None:
            return None
        safe = sid.replace("/", "_").replace("\\", "_")
        fname = f"{safe}_electro.png"
        fig.savefig(assets_dir / fname, dpi=130, bbox_inches="tight",
                    facecolor="white")
        plt.close(fig)
        return f"assets/{fname}"
    except Exception as e:
        logger.warning(f"Electropherogram PNG failed for {sid}: {e}")
        return None


# ── Batch overview charts ─────────────────────────────────────────────────────
def _save_batch_charts_png(selected_ids: list, assets_dir: Path) -> Optional[str]:
    """Render 3-panel batch charts (Total Amount / GQN-RIN / Concentration) as PNG."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from database import db_manager, get_qc_metrics_by_sample
        from config.settings import QC_CRITERIA

        _ST_MPL = {"Pass": "#4CAF50", "Warning": "#FF9800",
                   "Fail": "#F44336", "No Data": "#9E9E9E"}

        def _inst_rank(inst):
            if not inst:
                return 99
            il = inst.lower()
            if "qubit" in il:   return 0
            if "nano" in il:    return 1
            if "femto" in il:   return 2
            return 99

        # ── collect per-sample data ──────────────────────────────────
        per = {}
        for sid in selected_ids:
            d = {
                "total_amount": None, "amount_status": "No Data",
                "gqn_rin":      None, "rin_status":    "No Data",
                "concentration": None, "conc_status":  "No Data",
            }
            best_rank = 99
            try:
                with db_manager.session_scope() as session:
                    metrics = get_qc_metrics_by_sample(session, sid)
                    sorted_m = sorted(
                        metrics,
                        key=lambda m: m.measured_at or datetime.min,
                        reverse=True,
                    )
                    for m in sorted_m:
                        if m.total_amount is not None and d["total_amount"] is None:
                            d["total_amount"] = m.total_amount
                            d["amount_status"] = m.status or "No Data"
                        if m.gqn_rin is not None and d["gqn_rin"] is None:
                            d["gqn_rin"] = m.gqn_rin
                            d["rin_status"] = m.status or "No Data"
                        rank = _inst_rank(m.instrument)
                        if m.concentration is not None and rank < best_rank:
                            d["concentration"] = m.concentration
                            best_rank = rank
                            d["conc_status"] = m.status or "No Data"
            except Exception:
                pass
            per[sid] = d

        amounts = [per[sid]["total_amount"]  for sid in selected_ids]
        amt_st  = [per[sid]["amount_status"] for sid in selected_ids]
        rins    = [per[sid]["gqn_rin"]       for sid in selected_ids]
        rin_st  = [per[sid]["rin_status"]    for sid in selected_ids]
        concs   = [per[sid]["concentration"] for sid in selected_ids]
        conc_st = [per[sid]["conc_status"]   for sid in selected_ids]

        n = len(selected_ids)
        fig_w = max(10, n * 0.55 + 2)
        fig, axes = plt.subplots(3, 1, figsize=(fig_w, 10), facecolor="white")
        fig.subplots_adjust(hspace=0.60, left=0.07, right=0.97, top=0.96, bottom=0.07)

        short_ids = [sid.split("-")[-1] if "-" in sid else sid for sid in selected_ids]
        x = np.arange(n)

        def _draw(ax, values, statuses, title, ylabel, fmt, thresholds=None):
            colors = [_ST_MPL.get(s, "#9E9E9E") for s in statuses]
            bars = ax.bar(x, [v if v is not None else 0 for v in values],
                          color=colors, edgecolor="white", linewidth=0.5, alpha=0.88)
            if thresholds:
                for tv, tc, tl in thresholds:
                    ax.axhline(tv, color=tc, linewidth=1.0, linestyle="--",
                               alpha=0.85, label=tl)
                ax.legend(fontsize=7, loc="upper right",
                          framealpha=0.7, edgecolor="none")
            for bar, val in zip(bars, values):
                if val is not None and val > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height(),
                        fmt.format(val),
                        ha="center", va="bottom", fontsize=6.5, color="#333",
                    )
            ax.set_xticks(x)
            ax.set_xticklabels(short_ids, rotation=45, ha="right", fontsize=7.5)
            ax.set_ylabel(ylabel, fontsize=8)
            ax.tick_params(axis="y", labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_facecolor("#FAFAFA")
            ax.set_title(title, fontsize=9.5, fontweight="bold",
                         loc="left", color="#1A237E", pad=4)
            max_v = max((v for v in values if v is not None), default=0)
            if max_v > 0:
                ax.set_ylim(0, max_v * 1.30)

        _draw(axes[0], amounts, amt_st,
              "Total Amount (ng)", "Total Amount (ng)", "{:.0f}")

        rin_c = QC_CRITERIA.get("mRNA-seq", {}).get("RIN", {})
        rp, rw = rin_c.get("pass", 7.0), rin_c.get("warning", 5.0)
        _draw(axes[1], rins, rin_st,
              "GQN / RIN", "GQN / RIN", "{:.1f}",
              thresholds=[
                  (rp, _ST_MPL["Pass"],    f"Pass ≥{rp}"),
                  (rw, _ST_MPL["Warning"], f"Warning ≥{rw}"),
              ])

        _draw(axes[2], concs, conc_st,
              "Concentration (ng/µl)  [Qubit > NanoDrop > FemtoPulse]",
              "Concentration (ng/µl)", "{:.2f}")

        fname = "batch_charts.png"
        fig.savefig(assets_dir / fname, dpi=130, bbox_inches="tight",
                    facecolor="white")
        plt.close(fig)
        return f"assets/{fname}"
    except Exception as e:
        logger.warning(f"Batch charts PNG failed: {e}")
        return None


# ── QC criteria note ──────────────────────────────────────────────────────────
def _criteria_html(sample_type: str) -> str:
    from config.settings import QC_CRITERIA
    if sample_type == "WGS":
        c = QC_CRITERIA.get("WGS", {}).get("GQN", {})
        p, w = c.get("pass", 7.0), c.get("warning", 5.0)
        return (f"판정 기준 &nbsp;|&nbsp; GQN (Femto Pulse): Pass ≥ {p} / "
                f"Warning {w}–{p-0.1:.1f} / Fail < {w} &nbsp;|&nbsp; "
                f"농도 (Qubit/NanoDrop): 참고용 (판정 미사용)")
    if sample_type == "mRNA-seq":
        c = QC_CRITERIA.get("mRNA-seq", {}).get("RIN", {})
        p, w = c.get("pass", 7.0), c.get("warning", 5.0)
        return (f"판정 기준 &nbsp;|&nbsp; RIN (Femto Pulse): Pass ≥ {p} / "
                f"Warning {w}–{p-0.1:.1f} / Fail < {w} &nbsp;|&nbsp; "
                f"Total RNA (Qubit/NanoDrop): Pass ≥ 1,000 ng / Warning &lt; 1,000 ng")
    return ""


# ── Smear helpers (work with plain dicts, not ORM objects) ───────────────────
import re as _re


def _smear_span(rt) -> float:
    nums = [float(n) for n in _re.findall(r'\d+(?:\.\d+)?', str(rt).replace(',', ''))]
    return (nums[1] - nums[0]) if len(nums) >= 2 else 0.0


def _smear_low_high_d(step_smears: dict):
    """Return (pct_low, pct_high) from a dict-of-dicts smear map."""
    if not step_smears:
        return None, None
    total_key = max(step_smears, key=_smear_span)
    pct_low = pct_high = 0.0
    has_data = False
    for rng_text, sa in step_smears.items():
        if rng_text == total_key:
            continue
        if sa.get("pct_total") is None:
            continue
        text = str(rng_text).replace(',', '')
        if _re.search(r'marker|ladder', text, _re.IGNORECASE):
            continue
        nums = [float(n) for n in _re.findall(r'\d+(?:\.\d+)?', text)]
        if not nums:
            continue
        start = nums[0]
        end = nums[1] if len(nums) >= 2 else start * 5
        mid = (start + end) / 2
        has_data = True
        if mid < 1000:
            pct_low += sa["pct_total"]
        else:
            pct_high += sa["pct_total"]
    return (pct_low, pct_high) if has_data else (None, None)


def _widest_cv_d(step_smears: dict) -> str:
    if not step_smears:
        return "—"
    widest_key = max(step_smears, key=_smear_span)
    sa = step_smears.get(widest_key)
    if sa is None or sa.get("cv") is None:
        return "—"
    return f"{sa['cv']:.1f}"


def _compute_mqi_d(step_smears: dict) -> str:
    pct_low, pct_high = _smear_low_high_d(step_smears)
    if pct_high is not None and pct_low is not None:
        denom = pct_low + pct_high
        if denom > 0:
            return f"{pct_high / denom:.2f}"
    return "—"


# ── Section helpers ───────────────────────────────────────────────────────────
def _qc_table_html(metrics_dicts: list, smears: list, sample_type: str) -> str:
    """smears is a list of plain dicts (pre-converted from ORM objects)."""
    smear_by_step: dict = {}
    for sa in smears:
        smear_by_step.setdefault(sa["step"], {})[sa.get("range_text") or ""] = sa

    is_rna = "rna" in (sample_type or "").lower()

    cols = ["Step", "Instrument", "Conc\n(ng/µl)", "Vol\n(µl)", "Total\n(ng)",
            "GQN/\nRIN", "Avg Size\n(bp)", "%CV", "MQI", "Status", "Date"]

    hdr = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = ""
    for m in metrics_dicts:
        step_sm = smear_by_step.get(m.get("step", ""), {})
        cv  = _widest_cv_d(step_sm) if m.get("instrument") == "Femto Pulse" and is_rna else "—"
        mqi = _compute_mqi_d(step_sm) if m.get("instrument") == "Femto Pulse" and is_rna else "—"
        date_str = m["measured_at"].strftime("%Y-%m-%d") if m.get("measured_at") else "—"
        st = m.get("status") or "—"
        bg  = _ST_BG.get(st, "")
        fg  = _ST_FG.get(st, "")
        st_cell = (f'<td><span style="background:{bg};color:{fg};padding:1px 8px;'
                   f'border-radius:8px;font-weight:700">{st}</span></td>')
        rows_html += (
            f"<tr>"
            f'<td class="col-step">{m.get("step") or "—"}</td>'
            f"<td>{m.get('instrument') or '—'}</td>"
            f"<td>{_fmt(m.get('concentration'))}</td>"
            f"<td>{_fmt(m.get('volume'))}</td>"
            f"<td>{_fmt(m.get('total_amount'))}</td>"
            f"<td>{_fmt(m.get('gqn_rin'))}</td>"
            f"<td>{_fmt(m.get('avg_size'), 0)}</td>"
            f"<td>{cv}</td><td>{mqi}</td>"
            f"{st_cell}"
            f"<td>{date_str}</td>"
            f"</tr>\n"
        )
    if not rows_html:
        rows_html = f'<tr><td colspan="{len(cols)}" style="color:#999">No data</td></tr>'

    return f"<table><thead><tr>{hdr}</tr></thead><tbody>{rows_html}</tbody></table>"


def _smear_table_html(smears: list) -> str:
    """smears is a list of plain dicts (pre-converted from ORM objects)."""
    cols = ["Step", "Range", "% Total", "Avg Size (bp)", "%CV", "DQN"]
    hdr = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = ""
    for s in smears:
        rows_html += (
            f"<tr>"
            f'<td class="col-step">{s.get("step") or "—"}</td>'
            f'<td class="col-left">{s.get("range_text") or "—"}</td>'
            f"<td>{_fmt(s.get('pct_total'), 1)}</td>"
            f"<td>{_fmt(s.get('avg_size'), 0)}</td>"
            f"<td>{_fmt(s.get('cv'), 1)}</td>"
            f"<td>{_fmt(s.get('dqn'), 2)}</td>"
            f"</tr>\n"
        )
    if not rows_html:
        rows_html = f'<tr><td colspan="{len(cols)}" style="color:#999">No data</td></tr>'
    return f"<table><thead><tr>{hdr}</tr></thead><tbody>{rows_html}</tbody></table>"


# ── Main generator ────────────────────────────────────────────────────────────
def generate_html_report(
    selected_ids: List[str],
    snap_map: dict,
    output_dir: Path,
) -> None:
    """Build HTML report and save to output_dir/index.html with assets/ subfolder."""
    from database import (
        db_manager, get_qc_metrics_by_sample, get_smear_analyses_by_sample
    )

    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    counts = {"Pass": 0, "Warning": 0, "Fail": 0, "No Data": 0}
    for sid in selected_ids:
        st = snap_map.get(sid, {}).get("latest_status") or "No Data"
        counts[st] = counts.get(st, 0) + 1

    # ── Cover ──────────────────────────────────────────────────────────
    def _stat_box(label, n, bg, fg, border):
        return (f'<div class="stat" style="background:{bg};color:{fg};'
                f'border-color:{border}">{label}: {n}</div>')

    cover_html = f"""
<div class="card cover">
  <h1>NGS Sample QC Report</h1>
  <div class="subtitle">Generated: {now_str} &nbsp;|&nbsp; Total samples: {len(selected_ids)}</div>
  <div class="batch-stats">
    {_stat_box("Pass",    counts["Pass"],    "#E8F5E9","#2E7D32","#A5D6A7")}
    {_stat_box("Warning", counts["Warning"], "#FFF8E1","#BF360C","#FFCC80")}
    {_stat_box("Fail",    counts["Fail"],    "#FFEBEE","#B71C1C","#EF9A9A")}
    {_stat_box("No Data", counts["No Data"], "#F5F5F5","#757575","#BDBDBD")}
  </div>
</div>
"""

    # ── Batch overview table ────────────────────────────────────────────
    ov_rows = ""
    for sid in selected_ids:
        s = snap_map.get(sid, {})
        st = s.get("latest_status") or "No Data"
        ov_rows += (
            f"<tr>"
            f'<td class="col-step"><a href="#{sid}">{sid}</a></td>'
            f'<td class="col-left">{s.get("sample_name") or "—"}</td>'
            f"<td>{s.get('sample_type') or '—'}</td>"
            f"<td>{s.get('species') or '—'}</td>"
            f"<td>{s.get('material') or '—'}</td>"
            f"<td>{_badge(st)}</td>"
            f"</tr>\n"
        )
    overview_html = f"""
<div class="card">
  <div class="section-title"><span class="icon">📋</span> Batch Overview</div>
  <div class="toc" style="margin-bottom:16px">
    {"".join(f'<a href="#{sid}">{sid}</a>' for sid in selected_ids)}
  </div>
  <table>
    <thead><tr>
      <th>Sample ID</th><th>Name</th><th>Type</th><th>Species</th><th>Material</th><th>Status</th>
    </tr></thead>
    <tbody>{ov_rows}</tbody>
  </table>
</div>
"""

    # ── Batch charts ────────────────────────────────────────────────────
    batch_charts_path = _save_batch_charts_png(selected_ids, assets_dir)
    batch_charts_html = ""
    if batch_charts_path:
        batch_charts_html = f"""
<div class="card">
  <div class="section-title"><span class="icon">📊</span> Batch QC Charts</div>
  <div class="electro-wrap">
    <img src="{batch_charts_path}" alt="Batch QC Charts"
         style="max-height:none;width:100%">
  </div>
</div>
"""

    # ── Per-sample sections ─────────────────────────────────────────────
    sample_sections = ""
    for sid in selected_ids:
        snap = snap_map.get(sid, {"sample_id": sid})
        st = snap.get("latest_status") or "No Data"
        st_bg  = _ST_BG.get(st, "#F5F5F5")
        st_fg  = _ST_FG.get(st, "#555")

        # Load DB data
        metrics_dicts = []
        smears = []
        try:
            with db_manager.session_scope() as session:
                metrics = get_qc_metrics_by_sample(session, sid)
                metrics_dicts = [
                    {
                        "step":          m.step,
                        "instrument":    m.instrument,
                        "concentration": m.concentration,
                        "volume":        m.volume,
                        "total_amount":  m.total_amount,
                        "gqn_rin":       m.gqn_rin,
                        "avg_size":      m.avg_size,
                        "peak_size":     m.peak_size,
                        "status":        m.status,
                        "measured_at":   m.measured_at,
                    }
                    for m in metrics
                ]
                smears_raw = get_smear_analyses_by_sample(session, sid)
                smears = [
                    {
                        "step":      sa.step,
                        "range_text": sa.range_text,
                        "pct_total": sa.pct_total,
                        "avg_size":  sa.avg_size,
                        "cv":        sa.cv,
                        "dqn":       sa.dqn,
                    }
                    for sa in smears_raw
                ]
        except Exception as e:
            logger.error(f"DB load failed for {sid}: {e}")

        # Electropherogram
        electro_path = _save_electro_png(sid, assets_dir)
        electro_html = ""
        if electro_path:
            electro_html = f"""
  <div class="section-title" style="margin-top:20px">
    <span class="icon">📈</span> Electropherogram
  </div>
  <div class="electro-wrap">
    <img src="{electro_path}" alt="Electropherogram — {sid}">
  </div>
"""

        # Smear analysis
        smear_html = ""
        if smears:
            smear_html = f"""
  <div class="section-title" style="margin-top:20px">
    <span class="icon">🔬</span> Smear Analysis
  </div>
  {_smear_table_html(smears)}
"""

        # Criteria note
        criteria = _criteria_html(snap.get("sample_type", ""))
        criteria_html = f'<p class="criteria">{criteria}</p>' if criteria else ""

        info_parts = [
            f"Type: {snap.get('sample_type') or '—'}",
            f"Species: {snap.get('species') or '—'}",
            f"Material: {snap.get('material') or '—'}",
        ]
        if snap.get("description"):
            info_parts.append(snap["description"][:100])
        info_line = " &nbsp;|&nbsp; ".join(info_parts)

        sample_sections += f"""
<div class="sample-card" id="{sid}">
  <div class="sample-hdr">
    <div>
      <div class="sample-title">{sid} &nbsp;—&nbsp; {snap.get('sample_name') or ''}</div>
      <div class="sample-meta">{info_line}</div>
    </div>
    <div class="status-pill" style="background:{st_bg};color:{st_fg};border-color:{st_fg}40">
      {st}
    </div>
  </div>
  <div class="sample-body">
    <div class="section-title"><span class="icon">📊</span> QC Metrics</div>
    {_qc_table_html(metrics_dicts, smears, snap.get("sample_type", ""))}
    {criteria_html}
    {electro_html}
    {smear_html}
  </div>
</div>
"""

    # ── Assemble full HTML ──────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NGS Sample QC Report — {now_str}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="report-wrap">
  {cover_html}
  {overview_html}
  {batch_charts_html}
  {sample_sections}
</div>
</body>
</html>"""

    (output_dir / "ngs-sample-qc-report.html").write_text(html, encoding="utf-8")
    logger.info(f"HTML report saved: {output_dir / 'ngs-sample-qc-report.html'}")
