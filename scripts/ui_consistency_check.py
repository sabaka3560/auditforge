"""UI consistency guard for static/index.html.

Runs after every Write/Edit. Flags:
  - Native <select> elements (should be .gsel custom dropdowns)
  - Inline style colors outside the CSS variable system
  - Hard-coded background/color values not using var(--*)
  - Any emoji characters in visible text

Exit code 0 always (warnings only — never blocks the edit).
"""

import re
import sys

TARGET = "static/index.html"

# Only run for index.html edits
file_path = sys.argv[1] if len(sys.argv) > 1 else ""
if TARGET not in file_path.replace("\\", "/"):
    sys.exit(0)

try:
    with open(file_path, encoding="utf-8") as f:
        src = f.read()
except FileNotFoundError:
    sys.exit(0)

issues = []

# 1. Native <select> elements
native_selects = re.findall(r"<select[\s>]", src)
if native_selects:
    issues.append(
        f"  [SELECT] {len(native_selects)} native <select> element(s) found.\n"
        "           OS-rendered — use .gsel custom dropdown instead."
    )

# 2. Emoji characters in HTML (outside <script> and <style> blocks)
html_only = re.sub(r"<style[\s\S]*?</style>", "", src)
html_only = re.sub(r"<script[\s\S]*?</script>", "", html_only)
emojis = re.findall(
    r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FAFF]",
    html_only,
)
if emojis:
    issues.append(
        f"  [EMOJI]  {len(emojis)} emoji character(s) found in HTML markup.\n"
        "           Replace with inline SVG icons to stay within the design system."
    )

# 3. Hard-coded hex colours in style attributes (should use var(--*))
hex_inline = re.findall(r'style="[^"]*#[0-9a-fA-F]{3,6}[^"]*"', src)
if len(hex_inline) > 8:  # allow a small number (logos, gradients)
    issues.append(
        f"  [COLOR]  {len(hex_inline)} inline style(s) with hard-coded hex colours.\n"
        "           Prefer CSS variables (var(--blue), var(--t1), etc.)."
    )

# 4. backdrop-filter missing on glass elements (spot-check)
glass_panels = src.count('class="glass') + src.count("class='glass")
blur_defs = src.count("backdrop-filter")
# Each glass div needs at least one backdrop-filter rule (defined in CSS vars)
if glass_panels > 0 and blur_defs == 0:
    issues.append(
        "  [BLUR]   Glass panels present but no backdrop-filter found.\n"
        "           Add backdrop-filter:blur() to .glass in the CSS."
    )

if issues:
    print("\n\033[33m[ui-consistency]\033[0m warnings in", TARGET)
    for i in issues:
        print(i)
    print()
else:
    print(f"\033[32m[ui-consistency]\033[0m {TARGET} — OK")
