import pytest
import requests
import httpx
from smooth_api import _get_status_code

def test_get_status_code_requests():
    err = requests.exceptions.HTTPError(response=type('R', (), {'status_code': 502})())
    assert _get_status_code(err) == 502

def test_get_status_code_httpx():
    request = httpx.Request("GET", "http://localhost")
    response = httpx.Response(503, request=request)
    err = httpx.HTTPStatusError("error", request=request, response=response)
    assert _get_status_code(err) == 503

def test_get_status_code_unrelated_exception():
    err = ValueError("Something else")
    assert _get_status_code(err) is None
