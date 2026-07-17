from components import load_component_db


def test_known_knob_true_diameter():
    db = load_component_db()
    s = db.size_for("RoundBlackKnob")
    assert s.shape == "circle" and abs(s.d - 9.6) < 0.01


def test_substring_match_for_subclass():
    db = load_component_db()
    assert db.size_for("RoundSmallBlackSnapKnob").d == db.size_for("RoundSmallBlackKnob").d


def test_unknown_class_returns_none():
    assert load_component_db().size_for("TotallyMadeUpWidget") is None


def test_default_widgets():
    db = load_component_db()
    assert db.default_widget("param") == "RoundBlackKnob"
    assert db.default_widget("input") == "PJ301MPort"
    assert db.default_widget("output") == "PJ301MPort"
    assert db.default_widget("light") == "MediumLight<RedLight>"
