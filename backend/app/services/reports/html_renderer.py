"""Render canonical print documents as self-contained HTML."""

from __future__ import annotations

from html import escape

from app.services.reports.contracts.print_document import PlatformReportDocument


def _tone_badge_class(tone: str) -> str:
    return {
        'positive': 'badge-positive',
        'success': 'badge-positive',
        'warning': 'badge-warning',
        'negative': 'badge-danger',
        'danger': 'badge-danger',
        'error': 'badge-danger',
    }.get(tone, 'badge-neutral')


def _render_cover(block) -> str:
    meta_rows = ''.join(
        f'<div class="cover-meta-row"><span>{escape(key)}</span><strong>{escape(value)}</strong></div>'
        for key, value in block.metadata.items()
    )
    subtitle = f'<p class="cover-subtitle">{escape(block.subtitle)}</p>' if block.subtitle else ''
    return (
        '<section class="block cover-block">'
        f'<h1>{escape(block.title or "")}</h1>'
        f'{subtitle}'
        f'<div class="cover-meta">{meta_rows}</div>'
        '</section>'
    )


def _render_stat_grid(block) -> str:
    items = ''.join(
        '<div class="stat-card">'
        f'<div class="stat-label">{escape(item.label)}</div>'
        f'<div class="stat-value">{escape(item.value)}</div>'
        f'<div class="stat-tone {_tone_badge_class(item.tone)}">{escape(item.tone.title())}</div>'
        '</div>'
        for item in block.items
    )
    return f'<section class="block"><h2>{escape(block.title or "")}</h2><div class="stat-grid">{items}</div></section>'


def _render_prose(block) -> str:
    paragraphs = ''.join(
        f'<p>{escape(paragraph)}</p>'
        for paragraph in block.body.split('\n')
        if paragraph.strip()
    )
    return f'<section class="block"><h2>{escape(block.title or "")}</h2><div class="prose-body">{paragraphs}</div></section>'


def _render_table(block) -> str:
    head = ''.join(
        f'<th class="align-{escape(column.align)}">{escape(column.label)}</th>'
        for column in block.columns
    )
    body = ''.join(
        '<tr>' + ''.join(
            f'<td class="align-{escape(column.align)}">{escape("" if row.get(column.key) is None else str(row.get(column.key)))}</td>'
            for column in block.columns
        ) + '</tr>'
        for row in block.rows
    )
    return (
        f'<section class="block"><h2>{escape(block.title or "")}</h2>'
        '<table class="table-block"><thead><tr>'
        f'{head}</tr></thead><tbody>{body}</tbody></table></section>'
    )


def _render_heatmap_table(block) -> str:
    head = ''.join(f'<th>{escape(column)}</th>' for column in block.columns)
    body_rows = []
    for row in block.rows:
        cells = ''.join(
            f'<td class="heatmap-cell {_tone_badge_class(cell.tone)}">{escape("" if cell.value is None else str(cell.value))}</td>'
            for cell in row.cells
        )
        body_rows.append(f'<tr><th>{escape(row.label)}</th>{cells}</tr>')
    body = ''.join(body_rows)
    return (
        f'<section class="block"><h2>{escape(block.title or "")}</h2>'
        '<table class="table-block heatmap-table"><thead><tr><th></th>'
        f'{head}</tr></thead><tbody>{body}</tbody></table></section>'
    )


def _render_metric_bar_list(block) -> str:
    items = []
    for item in block.items:
        percent = 0 if item.max_value <= 0 else max(min(item.value / item.max_value * 100, 100), 0)
        items.append(
            '<div class="metric-row">'
            f'<div class="metric-label">{escape(item.label)}</div>'
            f'<div class="metric-value">{escape(str(item.value))}</div>'
            f'<div class="metric-track"><div class="metric-fill {_tone_badge_class(item.tone)}" style="width:{percent:.1f}%"></div></div>'
            '</div>'
        )
    return f'<section class="block"><h2>{escape(block.title or "")}</h2><div class="metric-list">{"".join(items)}</div></section>'


def _render_recommendation_list(block) -> str:
    items = ''.join(
        '<li class="recommendation-item">'
        f'<span class="priority-pill">{escape(item.priority)}</span>'
        f'<div><strong>{escape(item.title)}</strong><p>{escape(item.summary)}</p></div>'
        '</li>'
        for item in block.items
    )
    return f'<section class="block"><h2>{escape(block.title or "")}</h2><ul class="recommendation-list">{items}</ul></section>'


def _render_entity_table(block) -> str:
    return _render_table(block)


def _render_block(block) -> str:
    if block.type == 'cover':
        return _render_cover(block)
    if block.type == 'stat_grid':
        return _render_stat_grid(block)
    if block.type == 'prose':
        return _render_prose(block)
    if block.type == 'table':
        return _render_table(block)
    if block.type == 'heatmap_table':
        return _render_heatmap_table(block)
    if block.type == 'metric_bar_list':
        return _render_metric_bar_list(block)
    if block.type == 'recommendation_list':
        return _render_recommendation_list(block)
    if block.type == 'entity_table':
        return _render_entity_table(block)
    if block.type == 'page_break':
        return '<div class="page-break"></div>'
    return ''


def render_report_document(document: PlatformReportDocument) -> str:
    theme = document.theme
    blocks = ''.join(_render_block(block) for block in document.blocks)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{escape(document.title)}</title>
    <style>
      :root {{
        --accent: {theme.accent};
        --accent-muted: {theme.accent_muted};
        --border: {theme.border};
        --text-primary: {theme.text_primary};
        --text-secondary: {theme.text_secondary};
        --background: {theme.background};
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: var(--text-primary);
        background: var(--background);
        padding: 16mm 14mm;
      }}
      h1, h2, h3, p {{ margin: 0; }}
      .block {{ margin-bottom: 14px; page-break-inside: avoid; }}
      .cover-block {{
        background: linear-gradient(135deg, var(--accent), var(--accent-muted));
        color: white;
        padding: 16px;
        border-radius: 12px;
      }}
      .cover-subtitle {{ margin-top: 6px; opacity: 0.9; }}
      .cover-meta {{ margin-top: 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
      .cover-meta-row {{ background: rgba(255,255,255,0.16); border-radius: 8px; padding: 8px; }}
      .cover-meta-row span {{ display: block; font-size: 10px; text-transform: uppercase; opacity: 0.8; }}
      .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }}
      .stat-card {{ border: 1px solid var(--border); border-radius: 10px; padding: 10px; background: white; }}
      .stat-label {{ font-size: 11px; color: var(--text-secondary); text-transform: uppercase; }}
      .stat-value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
      .stat-tone {{ margin-top: 6px; font-size: 11px; }}
      .badge-positive {{ color: #047857; }}
      .badge-warning {{ color: #b45309; }}
      .badge-danger {{ color: #b91c1c; }}
      .badge-neutral {{ color: var(--text-secondary); }}
      .prose-body p + p {{ margin-top: 8px; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border: 1px solid var(--border); padding: 8px; vertical-align: top; font-size: 12px; }}
      th {{ background: #f8fafc; text-align: left; }}
      .align-right {{ text-align: right; }}
      .align-center {{ text-align: center; }}
      .metric-row {{ margin-bottom: 10px; }}
      .metric-label {{ font-size: 12px; color: var(--text-secondary); }}
      .metric-value {{ font-size: 14px; font-weight: 600; margin: 3px 0; }}
      .metric-track {{ height: 8px; background: #e5e7eb; border-radius: 999px; overflow: hidden; }}
      .metric-fill {{ height: 100%; background: var(--accent); }}
      .recommendation-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
      .recommendation-item {{ display: flex; gap: 10px; border: 1px solid var(--border); border-radius: 10px; padding: 10px; }}
      .priority-pill {{ min-width: 36px; height: 22px; border-radius: 999px; background: var(--accent-muted); color: var(--accent); display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }}
      .heatmap-cell {{ text-align: center; }}
      .page-break {{ page-break-before: always; height: 0; }}
      @page {{ size: A4; margin: 12mm 14mm; }}
    </style>
  </head>
  <body>
    {blocks}
  </body>
</html>"""
