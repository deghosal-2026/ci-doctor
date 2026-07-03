from app.resolver.extract import extract_snippet

SAMPLE_LOG = (
    "line 1: start\n"
    "line 2: running tests\n"
    "line 3: something happened\n"
    "line 4: ERROR: test failed\n"
    "line 5:   File test.py:42\n"
    "line 6:     assert False\n"
    "line 7:   AssertionError\n"
)


class TestExtractSnippet:
    def test_extracts_around_error(self):
        result = extract_snippet(SAMPLE_LOG, error_marker="ERROR")
        assert "line 4" in result
        assert "ERROR" in result

    def test_truncates_start(self):
        long = "\n".join(f"line {i}" for i in range(500))
        result = extract_snippet(long, error_marker="line 250")
        assert "line 50" in result
        assert " 250:" in result
        assert " 351:" in result

    def test_no_error_marker_returns_last_lines(self):
        result = extract_snippet("a\nb\nc", error_marker="NO_MATCH")
        assert "c" in result
