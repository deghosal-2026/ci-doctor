import click

from app.report.trend import load_decisions, aggregate
from app.report.cost import compute_cost_report


@click.group()
def cli():
    pass


@cli.command()
@click.option("--days", default=7, help="Number of days to look back")
@click.option("--decisions-path", default="decisions.yaml", help="Path to decisions.yaml")
@click.option("--hourly-rate", default=100, help="Engineer hourly rate for cost calc")
def report(days: int, decisions_path: str, hourly_rate: int):
    decisions = load_decisions(decisions_path, days=days)
    if not decisions:
        click.echo("No decisions found in the specified period.")
        return

    trend = aggregate(decisions)
    cost = compute_cost_report(decisions, hourly_rate=hourly_rate)

    click.echo(f"# ci-doctor Report -- Last {days} Days\n")
    click.echo("## Summary")
    click.echo(f"| Metric | Value |")
    click.echo(f"|---|---|")
    click.echo(f"| Total failures | {trend['total']} |")
    click.echo(f"| Auto-resolved | {trend['auto_resolved']} ({trend['auto_resolve_rate']}%) |")
    click.echo(f"| Human-resolved | {trend['human_resolved']} |")
    click.echo()
    click.echo("## Failures by Category")
    click.echo(f"| Category | Count |")
    click.echo(f"|---|---|")
    for cat, count in sorted(trend["by_category"].items()):
        click.echo(f"| {cat} | {count} |")
    click.echo()
    click.echo("## Top Recurring Signatures")
    for i, (sig, count) in enumerate(trend["top_signatures"], 1):
        click.echo(f"{i}. {sig} -- {count} occurrences")
    click.echo()
    click.echo("## Cost vs Value")
    click.echo(f"| Metric | Value |")
    click.echo(f"|---|---|")
    click.echo(f"| Token spend | ${cost['total_spend']:.2f} |")
    click.echo(f"| Engineer time saved | {cost['time_saved_minutes']} min |")
    click.echo(f"| Dollar value saved | ${cost['dollar_value']:.2f} |")
    click.echo(f"| Multiplier | {cost['multiplier']}x |")
