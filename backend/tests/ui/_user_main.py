"""Entry file for NiceGUI's `user` test fixture (see test_api_key_dialog.py):
it re-runs this per test, which re-registers the "/" page."""

import importlib

import app.ui.pages

importlib.reload(app.ui.pages)

from nicegui import ui

ui.run(storage_secret="test-secret")
