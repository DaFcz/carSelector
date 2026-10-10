"""Entry file for NiceGUI's `user` test fixture (see test_api_key_dialog.py):
it re-runs this per test, which re-registers the "/", "/admin" and
articles pages."""

import importlib

import app.ui.admin
import app.ui.articles_page
import app.ui.pages
import app.ui.shared_page

importlib.reload(app.ui.pages)

from nicegui import ui  # noqa: E402 - must follow the pages reload above

app.ui.admin.register_admin_page()
app.ui.articles_page.register_articles_pages()
app.ui.shared_page.register_shared_page()

ui.run(storage_secret="test-secret")
