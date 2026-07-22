"""Sidebar invariant: Platform Console must show the seven canonical sections."""
import os


REQUIRED_SECTIONS = {
    "HOME",
    "INTELLIGENCE ENGINE",
    "M&A ENGINE",
    "KNOWLEDGE",
    "PLATFORM",
    "DATA",
    "ADMIN",
}

LAYOUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "frontend", "src", "components", "Layout.js",
)


def test_sidebar_has_all_seven_sections():
    """Static guard: Layout.js must declare the seven canonical sidebar sections."""
    assert os.path.isfile(LAYOUT_PATH), f"Layout.js not found at {LAYOUT_PATH}"
    with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    missing = []
    for section in REQUIRED_SECTIONS:
        # Section appears as a string literal `label: 'INTELLIGENCE ENGINE'` etc.
        token = f"label: '{section}'"
        if token not in content:
            missing.append(section)
    assert not missing, f"Missing sidebar sections in Layout.js: {missing}"


def test_branding_is_intelligence_engine():
    """Header brand must say 'Intelligence Engine' (post-Agency-Tool rebrand)."""
    with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Intelligence Engine" in content, "Header brand 'Intelligence Engine' missing"
    assert "Platform Console" in content, "Subtitle 'Platform Console' missing"
