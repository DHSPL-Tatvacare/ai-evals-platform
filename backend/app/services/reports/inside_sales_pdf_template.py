"""Self-contained HTML template for inside sales PDF report generation."""

from __future__ import annotations

import html
from datetime import datetime


def _esc(value: object | None) -> str:
    return html.escape("" if value is None else str(value))


def _format_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return raw[:10]


def _score_color(score: float) -> str:
    if score >= 80:
        return "#16a34a"
    if score >= 65:
        return "#d97706"
    return "#dc2626"


def _priority_color(priority: str) -> str:
    return {
        "P0": "#dc2626",
        "P1": "#d97706",
        "P2": "#2563eb",
    }.get(priority, "#64748b")


def _section(title: str, body: str) -> str:
    return f"""
    <section style="margin-bottom:24px">
      <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.7px;margin:0 0 12px;color:#0f172a">{_esc(title)}</h2>
      {body}
    </section>
    """


def render_inside_sales_report_html(data: dict) -> str:
    metadata = data.get("metadata", {})
    summary = data.get("runSummary", {})
    dimensions = data.get("dimensionBreakdown", {})
    compliance = data.get("complianceBreakdown", {})
    flags = data.get("flagStats", {})
    agent_slices = data.get("agentSlices", {})
    narrative = data.get("narrative") or {}

    avg_score = summary.get("avgQaScore", 0)
    compliance_rate = summary.get("compliancePassRate", 0)
    verdict_distribution = summary.get("verdictDistribution", {})

    header = f"""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;background:#f8fafc;margin-bottom:24px">
      <div>
        <div style="font-size:10px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;color:#475569">Inside Sales Evaluation Report</div>
        <h1 style="font-size:22px;line-height:1.2;margin:6px 0 8px;color:#0f172a">{_esc(metadata.get('runName') or metadata.get('appId') or 'Inside Sales Report')}</h1>
        <div style="font-size:11px;color:#64748b">
          {_esc(metadata.get('evaluatedCalls', 0))} calls evaluated
          &middot; {_esc(metadata.get('llmModel') or 'Narrative unavailable')}
          &middot; {_esc(_format_date(metadata.get('createdAt')))}
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.7px">Avg QA Score</div>
        <div style="font-size:34px;font-weight:800;color:{_score_color(avg_score)}">{avg_score:.1f}</div>
        <div style="font-size:12px;color:#64748b">Compliance {compliance_rate:.0f}%</div>
      </div>
    </div>
    """

    summary_cards = f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
      <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div style="font-size:10px;text-transform:uppercase;color:#64748b">Total Calls</div>
        <div style="font-size:24px;font-weight:800;color:#0f172a">{summary.get('totalCalls', 0)}</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div style="font-size:10px;text-transform:uppercase;color:#64748b">Evaluated</div>
        <div style="font-size:24px;font-weight:800;color:#0f172a">{summary.get('evaluatedCalls', 0)}</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div style="font-size:10px;text-transform:uppercase;color:#64748b">Compliance Pass Rate</div>
        <div style="font-size:24px;font-weight:800;color:{_score_color(compliance_rate)}">{compliance_rate:.0f}%</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div style="font-size:10px;text-transform:uppercase;color:#64748b">Violations</div>
        <div style="font-size:24px;font-weight:800;color:#dc2626">{summary.get('complianceViolationCount', 0)}</div>
      </div>
    </div>
    """

    if narrative.get("executiveSummary"):
        summary_cards += f"""
        <div style="margin-top:14px;border-left:3px solid #2563eb;background:#eff6ff;border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.6;color:#1e293b">
          {_esc(narrative.get("executiveSummary"))}
        </div>
        """

    dimension_rows = "".join(
        f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">{_esc(dim.get('label', key))}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:{_score_color(dim.get('avg', 0))}">{dim.get('avg', 0):.1f}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{dim.get('min', 0):.1f}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{dim.get('max', 0):.1f}</td>
        </tr>
        """
        for key, dim in dimensions.items()
    )
    dimensions_section = _section(
        "QA Dimension Breakdown",
        f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
          <thead style="background:#f8fafc">
            <tr>
              <th style="padding:8px 10px;text-align:left">Dimension</th>
              <th style="padding:8px 10px;text-align:right">Avg</th>
              <th style="padding:8px 10px;text-align:right">Min</th>
              <th style="padding:8px 10px;text-align:right">Max</th>
            </tr>
          </thead>
          <tbody>{dimension_rows or '<tr><td colspan="4" style="padding:12px;color:#64748b">No dimension data.</td></tr>'}</tbody>
        </table>
        """,
    )

    compliance_rows = "".join(
        f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">{_esc(gate.get('label', key))}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{gate.get('passed', 0)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:#dc2626">{gate.get('failed', 0)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{(gate.get('passed', 0) / gate.get('total', 1) * 100) if gate.get('total', 0) else 100:.0f}%</td>
        </tr>
        """
        for key, gate in compliance.items()
    )
    compliance_section = _section(
        "Compliance Gates",
        f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
          <thead style="background:#f8fafc">
            <tr>
              <th style="padding:8px 10px;text-align:left">Gate</th>
              <th style="padding:8px 10px;text-align:right">Passed</th>
              <th style="padding:8px 10px;text-align:right">Failed</th>
              <th style="padding:8px 10px;text-align:right">Pass Rate</th>
            </tr>
          </thead>
          <tbody>{compliance_rows or '<tr><td colspan="4" style="padding:12px;color:#64748b">No compliance data.</td></tr>'}</tbody>
        </table>
        """,
    )

    def _flag_row(label: str, raw: dict) -> str:
        return f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">{_esc(label)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{raw.get('relevant', 0)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{raw.get('present', raw.get('attempted', 0))}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{raw.get('accepted', 0)}</td>
        </tr>
        """

    flag_section = _section(
        "Behavioral Signals & Outcomes",
        f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
          <thead style="background:#f8fafc">
            <tr>
              <th style="padding:8px 10px;text-align:left">Signal</th>
              <th style="padding:8px 10px;text-align:right">Relevant</th>
              <th style="padding:8px 10px;text-align:right">Present/Attempted</th>
              <th style="padding:8px 10px;text-align:right">Accepted</th>
            </tr>
          </thead>
          <tbody>
            {_flag_row('Escalations', flags.get('escalation', {}))}
            {_flag_row('Disagreements', flags.get('disagreement', {}))}
            {_flag_row('Tension Moments', {'relevant': flags.get('tension', {}).get('relevant', 0), 'present': sum(flags.get('tension', {}).get('bySeverity', {}).values()), 'accepted': 0})}
            {_flag_row('Meeting Setup', flags.get('meetingSetup', {}))}
            {_flag_row('Purchase', flags.get('purchaseMade', {}))}
            {_flag_row('Callback', flags.get('callbackScheduled', {}))}
            {_flag_row('Cross-sell', flags.get('crossSell', {}))}
          </tbody>
        </table>
        """,
    )

    agent_rows = "".join(
        f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">{_esc(agent.get('agentName', agent_id))}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{agent.get('callCount', 0)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:{_score_color(agent.get('avgQaScore', 0))}">{agent.get('avgQaScore', 0):.1f}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right">{agent.get('compliance', {}).get('passed', 0)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:#dc2626">{agent.get('compliance', {}).get('failed', 0)}</td>
        </tr>
        """
        for agent_id, agent in agent_slices.items()
    )
    agents_section = _section(
        "Agent Performance",
        f"""
        <table style="width:100%;border-collapse:collapse;font-size:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
          <thead style="background:#f8fafc">
            <tr>
              <th style="padding:8px 10px;text-align:left">Agent</th>
              <th style="padding:8px 10px;text-align:right">Calls</th>
              <th style="padding:8px 10px;text-align:right">Avg QA Score</th>
              <th style="padding:8px 10px;text-align:right">Compliance Pass</th>
              <th style="padding:8px 10px;text-align:right">Compliance Fail</th>
            </tr>
          </thead>
          <tbody>{agent_rows or '<tr><td colspan="5" style="padding:12px;color:#64748b">No agent data.</td></tr>'}</tbody>
        </table>
        """,
    )

    recommendation_items = "".join(
        f"""
        <li style="margin-bottom:8px">
          <span style="display:inline-block;min-width:34px;padding:2px 6px;border-radius:999px;background:{_priority_color(rec.get('priority', 'P2'))};color:#fff;font-size:10px;font-weight:700;margin-right:8px">{_esc(rec.get('priority', 'P2'))}</span>
          {_esc(rec.get('action', ''))}
        </li>
        """
        for rec in narrative.get("recommendations", [])
    )
    narrative_section = _section(
        "Narrative & Recommendations",
        f"""
        <div style="font-size:12px;line-height:1.7;color:#334155">
          <p><strong>Verdict Distribution:</strong> Strong {_esc(verdict_distribution.get('strong', 0))}, Good {_esc(verdict_distribution.get('good', 0))}, Needs Work {_esc(verdict_distribution.get('needsWork', 0))}, Poor {_esc(verdict_distribution.get('poor', 0))}</p>
          <p><strong>Flag Patterns:</strong> {_esc(narrative.get('flagPatterns') or 'Not available')}</p>
          <p><strong>Compliance Alerts:</strong> {_esc('; '.join(narrative.get('complianceAlerts', [])) or 'None')}</p>
          <h3 style="font-size:12px;text-transform:uppercase;letter-spacing:0.6px;margin-top:16px;color:#0f172a">Recommendations</h3>
          <ul style="padding-left:0;list-style:none;margin:10px 0 0">{recommendation_items or '<li style="color:#64748b">No recommendations.</li>'}</ul>
        </div>
        """,
    )

    body = header + _section("Executive Summary", summary_cards) + dimensions_section + compliance_section + flag_section + agents_section + narrative_section
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>{_esc(metadata.get('runName') or 'Inside Sales Report')}</title>
      </head>
      <body style="font-family:Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;padding:24px;color:#0f172a">
        {body}
      </body>
    </html>
    """
