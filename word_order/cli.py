import os

import click
from flask import current_app

from word_order.importer import WorkbookImportError, import_workbook
from word_order.storage import database_path


def register_cli(app):
    @app.cli.group("word-order")
    def word_order_commands():
        """Manage the English word-order game data."""

    @word_order_commands.command("sync-data")
    @click.argument("workbook_path", required=False, type=click.Path(exists=True, dir_okay=False))
    @click.option(
        "--deactivate-missing",
        is_flag=True,
        help="Deactivate words and challenges missing from the workbook.",
    )
    def sync_data(workbook_path, deactivate_missing):
        """Import or update game tables from a workbook."""
        source = workbook_path or current_app.config.get("WORD_ORDER_WORKBOOK") or os.path.join(
            current_app.root_path, "static", "data", "muster_structure.xlsx"
        )
        try:
            summary = import_workbook(
                source,
                database_path(),
                deactivate_missing=deactivate_missing,
            )
        except WorkbookImportError as error:
            raise click.ClickException(f"{error} ({error.rejected} rejected rows)") from error
        click.echo(
            "Sync complete: "
            + ", ".join(f"{key}={value}" for key, value in summary.items())
        )