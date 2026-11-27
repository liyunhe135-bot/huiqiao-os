"""M03 单测：全格式解析、调试隔离、按行截断、表结构摘要。全本地临时文件。"""

import pytest

from packages.doc_ingest.ingest import DebugDataIsolation, DocIngest
from packages.doc_ingest.parsers import ParserRegistry


@pytest.mark.ingest
def test_text_ingest(tmp_path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("第一行\n第二行", encoding="utf-8")
    result = DocIngest().ingest(p)
    assert "第一行" in result.markdown
    assert result.metadata["parser"] == "TextParser"


@pytest.mark.ingest
def test_markdown_ingest(tmp_path) -> None:
    p = tmp_path / "doc.md"
    p.write_text("# 标题\n内容", encoding="utf-8")
    result = DocIngest().ingest(p)
    assert "# 标题" in result.markdown


@pytest.mark.ingest
def test_csv_ingest_with_table_summary(tmp_path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("name,age\n张三,30\n李四,25\n", encoding="utf-8-sig")
    result = DocIngest().ingest(p)
    assert "| name | age |" in result.markdown
    assert len(result.tables) == 1
    assert result.tables[0].row_count == 2
    assert "2 行" in result.as_context()


@pytest.mark.ingest
def test_line_limit_truncates(tmp_path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("\n".join(f"行{i}" for i in range(100)), encoding="utf-8")
    result = DocIngest().ingest(p, max_lines=10)
    assert "已截断" in result.markdown
    assert "行99" not in result.markdown


@pytest.mark.ingest
def test_debug_data_marked(tmp_path) -> None:
    p = tmp_path / "debug.txt"
    p.write_text("测试内容", encoding="utf-8")
    result = DocIngest().ingest(p, is_debug=True)
    assert "调试数据" in result.as_context()


@pytest.mark.ingest
def test_debug_disabled(tmp_path) -> None:
    p = tmp_path / "debug.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(DebugDataIsolation):
        DocIngest(allow_debug=False).ingest(p, is_debug=True)


@pytest.mark.ingest
def test_base_dir_isolation(tmp_path) -> None:
    p = tmp_path / "secret.txt"
    p.write_text("x", encoding="utf-8")
    other = tmp_path / "allowed"
    other.mkdir()
    with pytest.raises(DebugDataIsolation):
        DocIngest().ingest(p, base_dir=other)


@pytest.mark.ingest
def test_binary_mock_parser(tmp_path) -> None:
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4 mock")
    result = DocIngest().ingest(p)
    assert "MockBinaryParser" in result.markdown


@pytest.mark.ingest
def test_unsupported_format(tmp_path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"data")
    with pytest.raises(Exception):
        DocIngest().ingest(p)
