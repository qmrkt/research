from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

from research.active_lp.reporting import AggregatedReport

SVG_WIDTH = 960
SVG_HEIGHT = 540
MARGIN_LEFT = 84
MARGIN_RIGHT = 32
MARGIN_TOP = 56
MARGIN_BOTTOM = 80
FIGURE_BG = "#fbfaf7"
TEXT_PRIMARY = "#1d1b18"
TEXT_MUTED = "#5d554a"
AXIS_COLOR = "#3d3a35"
GRID_COLOR = "#ddd7cf"
GRID_LIGHT = "#eee6dc"
ZERO_LINE = "#8a8177"
PRIMARY_BLUE = "#4A6FA5"
SECONDARY_BLUE = "#7C93BD"
DARK_BLUE = "#355B8C"
LIGHT_BLUE = "#A9B9D6"
ACCENT_ORANGE = "#C9714A"
SOFT_ORANGE = "#DDA07F"
WARM_RED = "#C75B5B"
STEEL_TEAL = "#2B6B7F"
STEEL_BLUE_MED = "#5A8FA8"
STEEL_BLUE_DARK = "#2B6B7F"


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _svg_document(elements: list[str], *, width: int = SVG_WIDTH, height: int = SVG_HEIGHT) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="{FIGURE_BG}"/>'
        f"{''.join(elements)}</svg>"
    )


def _title_elements(title: str, subtitle: str = "") -> list[str]:
    elems = [
        f'<text x="{MARGIN_LEFT}" y="28" font-size="20" font-family="Georgia, serif" fill="{TEXT_PRIMARY}">{escape(title)}</text>',
    ]
    if subtitle:
        elems.append(
            f'<text x="{MARGIN_LEFT}" y="46" font-size="11" font-family="Helvetica, Arial, sans-serif" fill="{TEXT_MUTED}">{escape(subtitle)}</text>'
        )
    return elems


def _histogram_svg(values: list[Decimal], *, title: str, subtitle: str, x_label: str) -> str:
    if not values:
        return _svg_document(_title_elements(title, subtitle))

    plot_width = SVG_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = SVG_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        min_value -= Decimal("1")
        max_value += Decimal("1")

    bin_count = min(20, max(6, int(len(values) ** Decimal("0.5"))))
    span = max_value - min_value
    bin_width = span / Decimal(bin_count)
    counts = [0 for _ in range(bin_count)]
    for value in values:
        index = int((value - min_value) / bin_width) if bin_width > 0 else 0
        if index >= bin_count:
            index = bin_count - 1
        counts[index] += 1
    max_count = max(counts) or 1

    elements = _title_elements(title, subtitle)
    x0 = MARGIN_LEFT
    y0 = SVG_HEIGHT - MARGIN_BOTTOM
    elements.append(f'<line x1="{x0}" y1="{y0}" x2="{SVG_WIDTH - MARGIN_RIGHT}" y2="{y0}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>')
    elements.append(f'<line x1="{x0}" y1="{MARGIN_TOP}" x2="{x0}" y2="{y0}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>')

    bar_gap = 4
    drawable_width = plot_width - bar_gap * (bin_count - 1)
    bar_width = max(drawable_width / bin_count, 4)
    for idx, count in enumerate(counts):
        height = plot_height * count / max_count
        x = x0 + idx * (bar_width + bar_gap)
        y = y0 - height
        elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}" fill="{PRIMARY_BLUE}" opacity="0.88"/>'
        )

    for tick_idx, tick_value in enumerate((min_value, Decimal("0"), max_value)):
        ratio = float((tick_value - min_value) / span)
        tick_x = x0 + plot_width * ratio
        elements.append(f'<line x1="{tick_x:.2f}" y1="{y0}" x2="{tick_x:.2f}" y2="{y0 + 6}" stroke="{AXIS_COLOR}" stroke-width="1"/>')
        elements.append(
            f'<text x="{tick_x:.2f}" y="{y0 + 22}" text-anchor="middle" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_value:.3f}</text>'
        )
    for tick_idx in range(0, max_count + 1, max(1, max_count // 4)):
        ratio = tick_idx / max_count
        tick_y = y0 - plot_height * ratio
        elements.append(f'<line x1="{x0 - 6}" y1="{tick_y:.2f}" x2="{x0}" y2="{tick_y:.2f}" stroke="{AXIS_COLOR}" stroke-width="1"/>')
        elements.append(
            f'<text x="{x0 - 10}" y="{tick_y + 4:.2f}" text-anchor="end" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_idx}</text>'
        )

    elements.append(
        f'<text x="{x0 + plot_width / 2:.2f}" y="{SVG_HEIGHT - 24}" text-anchor="middle" font-size="13" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(x_label)}</text>'
    )
    elements.append(
        f'<text x="22" y="{MARGIN_TOP + plot_height / 2:.2f}" transform="rotate(-90 22,{MARGIN_TOP + plot_height / 2:.2f})" text-anchor="middle" font-size="13" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">Scenario count</text>'
    )
    return _svg_document(elements)


def _bar_chart_svg(
    labels: list[str],
    values: list[Decimal],
    *,
    title: str,
    subtitle: str,
    x_label: str,
    y_label: str,
    colors: list[str] | None = None,
) -> str:
    if not labels or not values:
        return _svg_document(_title_elements(title, subtitle))

    default_colors = [PRIMARY_BLUE] * len(labels)
    bar_colors = colors if colors and len(colors) == len(labels) else default_colors

    bottom_margin = 72
    bar_pad_left = 40
    bar_pad_right = 20
    plot_width = SVG_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = SVG_HEIGHT - MARGIN_TOP - bottom_margin
    x0 = MARGIN_LEFT
    y0 = SVG_HEIGHT - bottom_margin
    max_abs_value = (max(abs(value) for value in values) or Decimal("1")) * Decimal("1.16")
    zero_y = y0 - plot_height / 2
    elements = _title_elements(title, subtitle)

    # Zero line and y-axis only, no grid
    elements.append(f'<line x1="{x0}" y1="{zero_y:.2f}" x2="{SVG_WIDTH - MARGIN_RIGHT}" y2="{zero_y:.2f}" stroke="{ZERO_LINE}" stroke-width="1"/>')
    elements.append(f'<line x1="{x0}" y1="{MARGIN_TOP}" x2="{x0}" y2="{y0}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>')

    # Wider bars with more horizontal padding
    n = len(labels)
    usable_width = plot_width - bar_pad_left - bar_pad_right
    bar_gap = max(usable_width * 0.08, 16)
    bar_width = (usable_width - bar_gap * (n - 1)) / n
    bar_width = max(bar_width, 20)

    for idx, (label, value) in enumerate(zip(labels, values)):
        x = x0 + bar_pad_left + idx * (bar_width + bar_gap)
        scaled_height = float(abs(value) / max_abs_value) * (plot_height / 2)
        fill = bar_colors[idx]
        if value >= 0:
            y = zero_y - scaled_height
        else:
            y = zero_y
        elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{scaled_height:.2f}" fill="{fill}" opacity="0.90" rx="2"/>'
        )
        # Horizontal x-axis labels
        label_x = x + bar_width / 2
        elements.append(
            f'<text x="{label_x:.2f}" y="{y0 + 18}" text-anchor="middle" font-size="10" '
            f'font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(label)}</text>'
        )
        # Value above (positive) or inside (negative)
        value_y = y - 8 if value >= 0 else y + scaled_height / 2 + 4
        elements.append(
            f'<text x="{label_x:.2f}" y="{value_y:.2f}" text-anchor="middle" font-size="9" '
            f'font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{value:.3f}</text>'
        )

    # Y-axis ticks (sparse: just min, zero, max)
    for tick_value in (-max_abs_value, Decimal("0"), max_abs_value):
        ratio = float((tick_value + max_abs_value) / (max_abs_value * 2))
        tick_y = y0 - plot_height * ratio
        elements.append(f'<line x1="{x0 - 5}" y1="{tick_y:.2f}" x2="{x0}" y2="{tick_y:.2f}" stroke="{AXIS_COLOR}" stroke-width="1"/>')
        elements.append(
            f'<text x="{x0 - 8}" y="{tick_y + 4:.2f}" text-anchor="end" font-size="11" '
            f'font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_value:.3f}</text>'
        )

    # Axis labels
    elements.append(
        f'<text x="{x0 + plot_width / 2:.2f}" y="{SVG_HEIGHT - 14}" text-anchor="middle" font-size="12" '
        f'font-family="Helvetica, Arial, sans-serif" fill="{TEXT_MUTED}">{escape(x_label)}</text>'
    )
    elements.append(
        f'<text x="22" y="{MARGIN_TOP + plot_height / 2:.2f}" transform="rotate(-90 22,{MARGIN_TOP + plot_height / 2:.2f})" '
        f'text-anchor="middle" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{TEXT_MUTED}">{escape(y_label)}</text>'
    )
    return _svg_document(elements)


def _line_chart_svg(
    points: list[dict[str, object]],
    *,
    title: str,
    subtitle: str,
    x_label: str,
    y_label: str,
    highlight_names: set[str] | None = None,
) -> str:
    if not points:
        return _svg_document(_title_elements(title, subtitle))

    ordered = sorted(points, key=lambda row: _to_decimal(row["x"]))
    x_values = [_to_decimal(row["x"]) for row in ordered]
    y_values = [_to_decimal(row["y"]) for row in ordered]
    x_min = min(x_values)
    x_max = max(x_values)
    if x_min == x_max:
        x_min -= Decimal("1")
        x_max += Decimal("1")
    y_min = min(y_values + [Decimal("0")])
    y_max = max(y_values + [Decimal("0")])
    if y_min == y_max:
        y_min -= Decimal("1")
        y_max += Decimal("1")

    x_pad = (x_max - x_min) * Decimal("0.06")
    y_pad = (y_max - y_min) * Decimal("0.12")
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad

    plot_width = SVG_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = SVG_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    x0 = MARGIN_LEFT
    y0 = SVG_HEIGHT - MARGIN_BOTTOM
    x_span = x_max - x_min
    y_span = y_max - y_min

    def scale_x(value: Decimal) -> float:
        return float(x0 + plot_width * ((value - x_min) / x_span))

    def scale_y(value: Decimal) -> float:
        return float(y0 - plot_height * ((value - y_min) / y_span))

    elements = _title_elements(title, subtitle)

    for tick_idx in range(6):
        ratio = Decimal(tick_idx) / Decimal(5)
        tick_value = y_min + y_span * ratio
        tick_y = scale_y(tick_value)
        elements.append(
            f'<line x1="{x0}" y1="{tick_y:.2f}" x2="{SVG_WIDTH - MARGIN_RIGHT}" y2="{tick_y:.2f}" stroke="{GRID_COLOR}" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{x0 - 10}" y="{tick_y + 4:.2f}" text-anchor="end" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_value:.3f}</text>'
        )
    for tick_idx in range(6):
        ratio = Decimal(tick_idx) / Decimal(5)
        tick_value = x_min + x_span * ratio
        tick_x = scale_x(tick_value)
        elements.append(
            f'<line x1="{tick_x:.2f}" y1="{MARGIN_TOP}" x2="{tick_x:.2f}" y2="{y0}" stroke="{GRID_LIGHT}" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{tick_x:.2f}" y="{y0 + 22}" text-anchor="middle" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_value:.4f}</text>'
        )

    zero_y = scale_y(Decimal("0"))
    elements.append(
        f'<line x1="{x0}" y1="{zero_y:.2f}" x2="{SVG_WIDTH - MARGIN_RIGHT}" y2="{zero_y:.2f}" stroke="{ZERO_LINE}" stroke-width="1.5"/>'
    )
    elements.append(f'<line x1="{x0}" y1="{MARGIN_TOP}" x2="{x0}" y2="{y0}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>')
    elements.append(f'<line x1="{x0}" y1="{y0}" x2="{SVG_WIDTH - MARGIN_RIGHT}" y2="{y0}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>')

    polyline_points = " ".join(f"{scale_x(x):.2f},{scale_y(y):.2f}" for x, y in zip(x_values, y_values))
    elements.append(
        f'<polyline fill="none" stroke="{PRIMARY_BLUE}" stroke-width="3" points="{polyline_points}" opacity="0.9"/>'
    )

    highlight_names = highlight_names or set()
    for row in ordered:
        x = scale_x(_to_decimal(row["x"]))
        y = scale_y(_to_decimal(row["y"]))
        name = str(row.get("label", ""))
        is_highlight = name in highlight_names
        fill = ACCENT_ORANGE if is_highlight else PRIMARY_BLUE
        radius = 6 if is_highlight else 4
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{fill}" opacity="0.95"/>')
        if is_highlight:
            text = escape(f"{name} ({_to_decimal(row['y']):.4f})")
            text_x = min(x + 10, SVG_WIDTH - MARGIN_RIGHT - 120)
            text_y = max(y - 10, MARGIN_TOP + 16)
            elements.append(
                f'<text x="{text_x:.2f}" y="{text_y:.2f}" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{text}</text>'
            )

    elements.append(
        f'<text x="{x0 + plot_width / 2:.2f}" y="{SVG_HEIGHT - 20}" text-anchor="middle" font-size="13" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(x_label)}</text>'
    )
    elements.append(
        f'<text x="22" y="{MARGIN_TOP + plot_height / 2:.2f}" transform="rotate(-90 22,{MARGIN_TOP + plot_height / 2:.2f})" text-anchor="middle" font-size="13" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(y_label)}</text>'
    )
    return _svg_document(elements)


def write_figure_pack(report: AggregatedReport, output_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    monte_carlo_rows = [row for row in report.scenario_rows if row["run_family"] == "monte_carlo"]
    deterministic_rows = [row for row in report.scenario_rows if row["run_family"] == "deterministic"]
    extreme_rows = [row for row in report.fairness_extreme_rows if row["direction"] == "absolute"][:10]

    histogram_path = out_dir / "fairness_gap_histogram.svg"
    deterministic_path = out_dir / "deterministic_fairness_bar.svg"
    extremes_path = out_dir / "fairness_extremes_bar.svg"

    histogram_svg = _histogram_svg(
        [_to_decimal(row["fairness_gap_nav_per_deposit"]) for row in monte_carlo_rows],
        title="Monte Carlo Fairness Gap Distribution",
        subtitle="",
        x_label="Fairness gap (late minus early NAV / deposit)",
    )
    histogram_path.write_text(histogram_svg, encoding="utf-8")

    deterministic_svg = _bar_chart_svg(
        [str(row["scenario_name"]) for row in deterministic_rows],
        [_to_decimal(row["fairness_gap_nav_per_deposit"]) for row in deterministic_rows],
        title="Deterministic Scenario Fairness Gaps",
        subtitle="",
        x_label="Scenario",
        y_label="Fairness gap (NAV / deposit)",
    )
    deterministic_path.write_text(deterministic_svg, encoding="utf-8")

    extremes_svg = _bar_chart_svg(
        [str(row["scenario_name"]) for row in extreme_rows],
        [_to_decimal(row["fairness_gap_nav_per_deposit"]) for row in extreme_rows],
        title="Largest Absolute Fairness Gaps",
        subtitle="",
        x_label="Scenario",
        y_label="Fairness gap (NAV / deposit)",
    )
    extremes_path.write_text(extremes_svg, encoding="utf-8")

    return {
        "fairness_gap_histogram_svg": histogram_path,
        "deterministic_fairness_bar_svg": deterministic_path,
        "fairness_extremes_bar_svg": extremes_path,
    }


def write_residual_weight_calibration_figure(
    rows: list[dict[str, object]],
    output_path: str | Path,
    *,
    highlight_name: str | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    points = [
        {
            "x": row["linear_lambda"],
            "y": row["mean_fairness_gap_nav_per_deposit"],
            "label": row["name"],
        }
        for row in rows
        if row.get("scheme") == "linear_lambda" and row.get("linear_lambda") not in ("", None)
    ]
    svg = _line_chart_svg(
        points,
        title="Residual Weight Calibration",
        subtitle="",
        x_label="Affine time-weight parameter (linear_lambda)",
        y_label="Mean fairness gap",
        highlight_names={highlight_name} if highlight_name else None,
    )
    path.write_text(svg, encoding="utf-8")
    return path


def write_residual_rule_comparison_figure(rows: list[dict[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [str(row["label"]) for row in rows]
    values = [_to_decimal(row["value"]) for row in rows]
    palette = [WARM_RED, ACCENT_ORANGE, SECONDARY_BLUE, DARK_BLUE]
    colors = [palette[index] if index < len(palette) else PRIMARY_BLUE for index in range(len(labels))]
    svg = _bar_chart_svg(
        labels,
        values,
        title="Residual Rule Comparison",
        subtitle="",
        x_label="Residual rule",
        y_label="Mean fairness gap",
        colors=colors,
    )
    path.write_text(svg, encoding="utf-8")
    return path


def write_layer_c_regime_comparison_figure(rows: list[dict[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [str(row["label"]) for row in rows]
    values = [_to_decimal(row["value"]) for row in rows]
    # Single hue, darker for the invariant-failures bar (last)
    bar_colors = [STEEL_BLUE_MED] * len(labels)
    if len(bar_colors) > 0:
        bar_colors[-1] = STEEL_BLUE_DARK
    svg = _bar_chart_svg(
        labels,
        values,
        title="Layer C Low-Tail Drift",
        subtitle="",
        x_label="Layer C comparison metric",
        y_label="Difference",
        colors=bar_colors,
    )
    path.write_text(svg, encoding="utf-8")
    return path


def write_low_tail_failure_trace_figure(rows: list[dict[str, object]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(
            _svg_document(_title_elements("Representative Low-Tail Failure Trace", "No data.")),
            encoding="utf-8",
        )
        return path

    width = SVG_WIDTH
    height = 640
    left = MARGIN_LEFT
    right = MARGIN_RIGHT
    top_panel_top = 112
    panel_height = 168
    panel_gap = 56
    bottom_panel_top = top_panel_top + panel_height + panel_gap
    panel_width = width - left - right
    top_panel_bottom = top_panel_top + panel_height
    bottom_panel_bottom = bottom_panel_top + panel_height
    label_y = height - 62

    ordered = sorted(rows, key=lambda row: int(row["event_index"]))
    event_count = len(ordered)

    reserve_reference = [_to_decimal(row["reference_reserve_margin"]) for row in ordered]
    reserve_layer_c = [_to_decimal(row["layer_c_reserve_margin"]) for row in ordered]
    min_reference = [_to_decimal(row["reference_min_margin"]) for row in ordered]
    min_layer_c = [_to_decimal(row["layer_c_min_margin"]) for row in ordered]

    max_reserve = max(reserve_reference + reserve_layer_c + [Decimal("1")])
    reserve_min = Decimal("0")
    reserve_max = max_reserve * Decimal("1.08")
    if reserve_max == reserve_min:
        reserve_max += Decimal("1")

    min_min = min(min_reference + min_layer_c + [Decimal("0")])
    min_max = max(min_reference + min_layer_c + [Decimal("0")])
    min_pad = max((min_max - min_min) * Decimal("0.12"), Decimal("6"))
    min_domain_min = min_min - min_pad
    min_domain_max = min_max + min_pad
    if min_domain_max == min_domain_min:
        min_domain_max += Decimal("1")

    def scale_x(index: int) -> float:
        if event_count == 1:
            return float(left + panel_width / 2)
        return float(left + panel_width * (Decimal(index) / Decimal(event_count - 1)))

    def scale_y(value: Decimal, domain_min: Decimal, domain_max: Decimal, panel_top: int, panel_bottom: int) -> float:
        span = domain_max - domain_min
        return float(panel_bottom - (panel_bottom - panel_top) * ((value - domain_min) / span))

    def panel_line(
        values: list[Decimal],
        *,
        domain_min: Decimal,
        domain_max: Decimal,
        panel_top: int,
        panel_bottom: int,
        stroke: str,
        dash: str | None = None,
    ) -> str:
        points = " ".join(
            f"{scale_x(idx):.2f},{scale_y(value, domain_min, domain_max, panel_top, panel_bottom):.2f}"
            for idx, value in enumerate(values)
        )
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline fill="none" stroke="{stroke}" stroke-width="3"{dash_attr} points="{points}" opacity="0.96"/>'

    elements = _title_elements("Representative Low-Tail Failure Trace")

    for panel_top, panel_bottom, domain_min, domain_max, ylabel in (
        (top_panel_top, top_panel_bottom, reserve_min, reserve_max, "Reserve margin"),
        (bottom_panel_top, bottom_panel_bottom, min_domain_min, min_domain_max, "Min cohort margin"),
    ):
        for tick_idx in range(5):
            ratio = Decimal(tick_idx) / Decimal(4)
            tick_value = domain_min + (domain_max - domain_min) * ratio
            tick_y = scale_y(tick_value, domain_min, domain_max, panel_top, panel_bottom)
            elements.append(
                f'<line x1="{left}" y1="{tick_y:.2f}" x2="{width - right}" y2="{tick_y:.2f}" stroke="{GRID_COLOR}" stroke-width="1"/>'
            )
            elements.append(
                f'<text x="{left - 10}" y="{tick_y + 4:.2f}" text-anchor="end" font-size="11" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{tick_value:.1f}</text>'
            )
        elements.append(
            f'<line x1="{left}" y1="{panel_top}" x2="{left}" y2="{panel_bottom}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>'
        )
        elements.append(
            f'<line x1="{left}" y1="{panel_bottom}" x2="{width - right}" y2="{panel_bottom}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>'
        )
        if domain_min <= 0 <= domain_max:
            zero_y = scale_y(Decimal("0"), domain_min, domain_max, panel_top, panel_bottom)
            elements.append(
                f'<line x1="{left}" y1="{zero_y:.2f}" x2="{width - right}" y2="{zero_y:.2f}" stroke="{ZERO_LINE}" stroke-width="1.4"/>'
            )
        elements.append(
            f'<text x="24" y="{(panel_top + panel_bottom) / 2:.2f}" transform="rotate(-90 24,{(panel_top + panel_bottom) / 2:.2f})" text-anchor="middle" font-size="12" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(ylabel)}</text>'
        )

    top_reference = PRIMARY_BLUE
    top_layer_c = SECONDARY_BLUE
    bottom_reference = ACCENT_ORANGE
    bottom_layer_c = SOFT_ORANGE

    elements.append(
        panel_line(
            reserve_reference,
            domain_min=reserve_min,
            domain_max=reserve_max,
            panel_top=top_panel_top,
            panel_bottom=top_panel_bottom,
            stroke=top_reference,
        )
    )
    elements.append(
        panel_line(
            reserve_layer_c,
            domain_min=reserve_min,
            domain_max=reserve_max,
            panel_top=top_panel_top,
            panel_bottom=top_panel_bottom,
            stroke=top_layer_c,
            dash="9 6",
        )
    )
    elements.append(
        panel_line(
            min_reference,
            domain_min=min_domain_min,
            domain_max=min_domain_max,
            panel_top=bottom_panel_top,
            panel_bottom=bottom_panel_bottom,
            stroke=bottom_reference,
        )
    )
    elements.append(
        panel_line(
            min_layer_c,
            domain_min=min_domain_min,
            domain_max=min_domain_max,
            panel_top=bottom_panel_top,
            panel_bottom=bottom_panel_bottom,
            stroke=bottom_layer_c,
            dash="9 6",
        )
    )

    for idx, row in enumerate(ordered):
        x = scale_x(idx)
        label = str(row["event_label"])
        elements.append(
            f'<line x1="{x:.2f}" y1="{top_panel_top}" x2="{x:.2f}" y2="{bottom_panel_bottom}" stroke="{GRID_LIGHT}" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{x:.2f}" y="{label_y}" text-anchor="end" transform="rotate(-35 {x:.2f},{label_y})" font-size="11" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(label)}</text>'
        )
        for values, domain_min, domain_max, panel_top, panel_bottom, fill in (
            (reserve_reference, reserve_min, reserve_max, top_panel_top, top_panel_bottom, top_reference),
            (reserve_layer_c, reserve_min, reserve_max, top_panel_top, top_panel_bottom, top_layer_c),
            (min_reference, min_domain_min, min_domain_max, bottom_panel_top, bottom_panel_bottom, bottom_reference),
            (min_layer_c, min_domain_min, min_domain_max, bottom_panel_top, bottom_panel_bottom, bottom_layer_c),
        ):
            y = scale_y(values[idx], domain_min, domain_max, panel_top, panel_bottom)
            elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="{fill}" opacity="0.95"/>')

    legend_x = left
    legend_y = 56
    legend = [
        ("Reference", top_reference, None),
        ("Layer C", top_layer_c, "9 6"),
        ("Ref. min cohort", bottom_reference, None),
        ("Layer C min cohort", bottom_layer_c, "9 6"),
    ]
    for idx, (label, color, dash) in enumerate(legend):
        y = legend_y + idx * 15
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        elements.append(
            f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 20}" y2="{y}" stroke="{color}" stroke-width="3"{dash_attr}/>'
        )
        elements.append(
            f'<text x="{legend_x + 26}" y="{y + 4}" font-size="10" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">{escape(label)}</text>'
        )

    elements.append(
        f'<text x="{left + panel_width / 2:.2f}" y="{height - 18}" text-anchor="middle" font-size="13" font-family="Helvetica, Arial, sans-serif" fill="{AXIS_COLOR}">Event sequence</text>'
    )

    path.write_text(_svg_document(elements, width=width, height=height), encoding="utf-8")
    return path
