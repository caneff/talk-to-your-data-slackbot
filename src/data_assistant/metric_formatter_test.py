import data_assistant.metric_formatter as metric_formatter
import data_assistant.semantic_layer.schema as schema


def test_format_metric_value_renders_money() -> None:
    assert (
        metric_formatter.format_metric_value(1234.5, schema.MetricKind.MONEY)
        == "$1,234.50"
    )


def test_format_metric_value_renders_count_without_currency() -> None:
    assert (
        metric_formatter.format_metric_value(1234, schema.MetricKind.COUNT) == "1,234"
    )
