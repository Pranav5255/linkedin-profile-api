from __future__ import annotations

LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LinkedIn Profile API</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f1216;
      --fg: #e8eaed;
      --muted: #9aa3ad;
      --btn: #e8eaed;
      --btn-fg: #0f1216;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      min-height: 100%;
      background: var(--bg);
      color: var(--fg);
      font: 16px/1.5 ui-sans-serif, system-ui, sans-serif;
    }
    main {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      max-width: 36rem;
      padding: 2.5rem 1.5rem;
      margin: 0 auto;
      text-align: center;
    }
    h1 {
      font-size: 1.75rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      margin: 0 0 0.75rem;
    }
    p {
      margin: 0 0 1.75rem;
      color: var(--muted);
    }
    code {
      color: var(--fg);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }
    a.button {
      display: inline-block;
      padding: 0.7rem 1.15rem;
      background: var(--btn);
      color: var(--btn-fg);
      text-decoration: none;
      font-weight: 600;
      border-radius: 0.4rem;
    }
    a.button:focus-visible {
      outline: 2px solid var(--fg);
      outline-offset: 3px;
    }
  </style>
</head>
<body>
  <main>
    <h1>LinkedIn Profile API</h1>
    <p>Send a LinkedIn <code>/in/{slug}</code> URL. Get indented JSON back — name, experience, education, and the other public sections the session can see.</p>
    <a class="button" href="/docs">Set API key</a>
  </main>
</body>
</html>
"""
