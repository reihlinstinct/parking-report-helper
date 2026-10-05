### Manual live-site diagnostic

The separate **Jerusalem 106 read-only probe** Actions workflow runs only via
`workflow_dispatch`. It loads the official page once with ordinary headless
Chromium, reads configured field labels in the main frame, and closes. It does
not enter values, upload photos, interact with captcha, submit, retry, or use
stealth settings. HTTP blocks and verification widgets are reported as results
and stop inspection. Logs and the job summary show the HTTP status and either
found/missing labels or the blocking result. A green job means the diagnostic
ran, not that access or selectors worked. Embedded forms are not inspected.

GitHub requires a manually dispatched workflow to exist on the default branch
before it can be selected in Actions. Until this workflow is merged, the PR's
ordinary tests remain local/mock-only and no live diagnostic may be available.
Once available: Actions > Jerusalem 106 read-only probe > Run workflow. Run it
only when needed; it must never be added to automatic CI triggers.
