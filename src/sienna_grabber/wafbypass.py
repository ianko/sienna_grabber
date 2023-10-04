# Bypass the AWS WAF in front of the GraphQL endpoint.
from playwright.sync_api import sync_playwright


class WAFBypass:
    """Bypass the AWS WAF in front of the GraphQL endpoint."""

    def intercept_request(self, request):
        """Find the GraphQL request and save the headers."""
        if request.resource_type == "xhr" and request.url.endswith("/graphql"):
            self.valid_headers = request.headers
            # Just in case the request JSON is needed later.
            # pprint(request.post_data_json)
        return request

    def get_headers(self) -> None:
        """Run a browser to get valid headers for a WAF bypass."""
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.on("request", self.intercept_request)
            page.goto("https://www.toyota.com/search-inventory/")
            page.get_by_placeholder("ZIP Code").click()
            page.get_by_placeholder("ZIP Code").fill("90210")
            page.get_by_placeholder("ZIP Code").press("Enter")
            page.wait_for_load_state("networkidle")
            browser.close()

    def run(self):
        """Return the valid headers to bypass the WAF."""
        self.get_headers()
        return self.valid_headers
