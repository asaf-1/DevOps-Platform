import pytest

from platform_api.catalog import Catalog, CatalogError


def test_loads_the_three_phase1_types(catalog: Catalog) -> None:
    assert set(catalog.types) == {"s3-bucket", "dynamodb-table", "k8s-namespace"}
    for ctype in catalog.types.values():
        assert ctype.module.startswith("infra/terraform/modules/")
        assert ctype.policy_set == "terraform-default"
        assert ctype.approval_required is True
        assert "name" in ctype.input_schema["properties"]


def test_defaults_are_filled(catalog: Catalog) -> None:
    filled = catalog.validate_inputs(
        "s3-bucket", {"name": "demo-uploads", "team": "web", "cost_center": "cc-100"}
    )
    assert filled["versioning"] is True
    assert filled["retention"] == "90d"


@pytest.mark.parametrize(
    "inputs",
    [
        {"name": "UPPER", "team": "web", "cost_center": "cc-100"},
        {"name": "ab", "team": "web", "cost_center": "cc-100"},
        {"name": "demo", "team": "web"},
        {"name": "demo", "team": "web", "cost_center": "cc-100", "retention": "7d"},
        {"name": "demo", "team": "web", "cost_center": "cc-100", "public": True},
    ],
)
def test_bad_inputs_are_rejected(catalog: Catalog, inputs: dict) -> None:
    with pytest.raises(CatalogError):
        catalog.validate_inputs("s3-bucket", inputs)


def test_unknown_type(catalog: Catalog) -> None:
    with pytest.raises(CatalogError):
        catalog.get("rds-instance")
