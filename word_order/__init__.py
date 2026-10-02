import os

from flask import Blueprint, current_app, jsonify, request

from word_order.importer import WorkbookImportError, synchronize_if_changed
from word_order.storage import database_path


word_order_bp = Blueprint(
    "word_order",
    __name__,
    url_prefix="/games/word-order",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


@word_order_bp.before_request
def synchronize_content():
    workbook_path = current_app.config.get("WORD_ORDER_WORKBOOK") or os.path.join(
        current_app.root_path, "static", "data", "muster_structure.xlsx"
    )
    try:
        synchronize_if_changed(workbook_path, database_path())
    except (OSError, WorkbookImportError) as error:
        current_app.logger.exception("Could not synchronize word-order data")
        return jsonify({"error": str(error)}), 500


from word_order import routes  # noqa: E402,F401