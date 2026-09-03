def test_htmx_demo_returns_swapped_fragment(client):
    response = client.get("/htmx-demo/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b"Loaded via HTMX" in response.content


def test_htmx_demo_response_has_no_base_html_chrome(client):
    """The endpoint always returns just the fragment (never base.html), so
    an HTMX swap can't accidentally pull in a second <html>/<nav>/<body>."""
    response = client.get("/htmx-demo/", HTTP_HX_REQUEST="true")

    content = response.content.decode()
    assert "<html" not in content
    assert "<nav " not in content and "<nav>" not in content


def test_home_page_contains_htmx_trigger_button(client):
    response = client.get("/")

    content = response.content.decode()
    assert 'hx-get="/htmx-demo/"' in content
    assert 'id="htmx-demo-result"' in content
