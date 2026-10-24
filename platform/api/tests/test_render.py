from platform_api.catalog import Catalog
from platform_api.render import Renderer, tf_ident, tf_string


def test_filters() -> None:
    assert tf_ident("r-20261024-ab12") == "r-20261024-ab12"
    assert tf_ident("Weird Name!") == "weird_name_"
    assert tf_ident("123") == "r_123"
    assert tf_string(None) == "null"
    assert tf_string('a"b') == '"a\\"b"'


def test_render_s3(catalog: Catalog) -> None:
    text = Renderer(catalog).render(
        "s3-bucket",
        "r-abc123",
        {"name": "demo-uploads", "team": "web", "cost_center": "cc-100", "retention": "30d"},
    )
    assert 'module "r-abc123"' in text
    assert 'source = "../../../modules/s3-bucket"' in text
    assert 'name       = "demo-uploads"' in text
    assert "versioning = true" in text
    assert 'retention  = "30d"' in text
    assert '"request-id"  = "r-abc123"' in text
    assert '"managed-by"  = "platform"' in text
    assert 'output "r-abc123"' in text
    assert text.endswith("\n")


def test_render_dynamodb_optional_fields(catalog: Catalog) -> None:
    text = Renderer(catalog).render(
        "dynamodb-table",
        "r-def456",
        {"name": "orders", "team": "web", "cost_center": "cc-100", "hash_key": "order_id"},
    )
    assert "range_key              = null" in text
    assert "ttl_attribute          = null" in text
    assert 'size                   = "small"' in text
    assert "point_in_time_recovery = true" in text


def test_render_namespace(catalog: Catalog) -> None:
    text = Renderer(catalog).render(
        "k8s-namespace",
        "r-789abc",
        {"name": "team-web-dev", "team": "web", "cost_center": "cc-100", "size": "large"},
    )
    assert 'source = "../../../modules/k8s-namespace"' in text
    assert 'size = "large"' in text
