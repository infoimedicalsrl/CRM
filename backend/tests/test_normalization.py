from app.normalization import normalize_product_code, normalize_unit_code


def test_product_code_normalization_ignores_spaces_and_case():
    assert normalize_product_code("BE-HLS7050") == normalize_product_code("BE-HLS 7050")
    assert normalize_product_code("BE-HLS7050") == normalize_product_code("be-hls7050")


def test_c62_is_pieces():
    assert normalize_unit_code("C62") == "PZ"
    assert normalize_unit_code("pz") == "PZ"
