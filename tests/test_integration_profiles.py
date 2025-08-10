import sys
import types
import pytest

from workflow.flow import Flow, Meta, Defaults, Step
from workflow.runner import Runner
from workflow import actions
from workflow import gui_tools


@pytest.mark.parametrize(
    "profile,dpi,lang",
    [
        ("physical", 96, "eng"),
        ("vdi", 120, "jpn"),
    ],
)
def test_environment_integration(monkeypatch, profile, dpi, lang):
    """Run a minimal flow ensuring DPI, language and profile are respected."""

    # Force a deterministic DPI value
    monkeypatch.setattr(gui_tools, "_screen_dpi", lambda: dpi)

    # Provide a fake OCR backend that echoes the requested language
    pytesseract = types.SimpleNamespace(
        image_to_string=lambda img, lang=None: f"text-{lang}",
        get_languages=lambda config="": ["eng", "jpn"],
    )
    sys.modules["pytesseract"] = pytesseract

    # Avoid file system access when opening images
    monkeypatch.setattr("PIL.Image.open", lambda path: object())

    runner = Runner()

    # Register helper actions
    runner.register_action("coords", lambda step, ctx: gui_tools.capture_coordinates())
    runner.register_action("ocr", actions.ocr_read)
    runner.register_action("current_profile", lambda step, ctx: ctx.globals["profile"])

    flow = Flow(
        version="1.0",
        meta=Meta(name="integration"),
        defaults=Defaults(envProfile=profile),
        steps=[
            Step(id="c", action="coords", out="coords"),
            Step(
                id="o",
                action="ocr",
                params={"path": "dummy.png", "lang": lang},
                out="text",
            ),
            Step(id="p", action="current_profile", out="profile"),
        ],
    )

    result = runner.run_flow(flow, {})
    assert result["coords"]["dpi"] == dpi
    assert result["text"] == f"text-{lang}"
    assert result["profile"] == profile
