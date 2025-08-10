import json
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
import rpa_main_ui


def test_default_role_hides_advanced(monkeypatch, tmp_path):
    monkeypatch.setattr(rpa_main_ui.Path, "home", lambda: tmp_path)
    app = QApplication([])
    w = rpa_main_ui.MainWindow()
    assert not w.header.adv_chk.isChecked()
    assert not w.prop_panel.advanced_group.isVisible()
    assert all(item.isHidden() for item in w.action_palette._adv_items)
    w.close()
    app.quit()


def test_admin_role_shows_advanced(monkeypatch, tmp_path):
    cfg_dir = tmp_path / '.config' / 'rpa_project'
    cfg_dir.mkdir(parents=True)
    (cfg_dir / 'config.json').write_text(json.dumps({'role': 'admin'}))
    monkeypatch.setattr(rpa_main_ui.Path, "home", lambda: tmp_path)
    app = QApplication([])
    w = rpa_main_ui.MainWindow()
    assert w.header.adv_chk.isChecked()
    assert w.prop_panel.advanced_group.isVisible()
    w.header.adv_chk.setChecked(False)
    assert not w.prop_panel.advanced_group.isVisible()
    assert all(item.isHidden() for item in w.action_palette._adv_items)
    w.close()
    app.quit()
