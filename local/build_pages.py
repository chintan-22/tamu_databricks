"""Wrap dashboard/app.html (a page fragment) into a standalone dashboard/index.html for GitHub Pages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
body = (ROOT / "dashboard" / "app.html").read_text(encoding="utf-8")
head_end = body.index("</style>") + len("</style>")
page = (
    "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
    "[hidden]{display:none!important}img{max-width:100%}</style>\n"
    + body[:head_end] + "\n</head>\n<body>\n" + body[head_end:] + "\n</body>\n</html>\n"
)
(ROOT / "dashboard" / "index.html").write_text(page, encoding="utf-8")
print("wrote dashboard/index.html")
