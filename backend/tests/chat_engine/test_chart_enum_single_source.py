def test_typer_reuses_manifest_chart_enums():
    from app.services.chat_engine import result_set_typer as t
    from app.services.chat_engine import manifest as m

    # same object identity → single source of truth, cannot drift
    assert t.ColumnRole is m.ColumnRole
    assert t.DataType is m.DataType
    assert t.SemanticType is m.SemanticType
