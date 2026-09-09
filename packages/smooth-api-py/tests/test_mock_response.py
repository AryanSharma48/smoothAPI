from smooth_api import MockResponse


def test_mock_response_json():
    content = {"message": "circuit is open"}
    response = MockResponse(status_code=503, content=content)

    assert response.json() == content


def test_mock_response_text():
    import json

    content = {"message": "circuit is open"}
    response = MockResponse(status_code=503, content=content)

    assert json.loads(response.text) == content


def test_mock_response_ok():
    assert MockResponse(status_code=200, content={}).ok is True
    assert MockResponse(status_code=399, content={}).ok is True
    assert MockResponse(status_code=400, content={}).ok is False
    assert MockResponse(status_code=503, content={}).ok is False


def test_mock_response_status_code():
    response = MockResponse(status_code=503, content={})

    assert response.status_code == 503
