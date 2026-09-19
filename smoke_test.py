"""
Headless smoke test for a running Shiny dashboard: connect over Shiny's websocket, send
the given input values, ask for every output on the page, and report any output errors.

    python smoke_test.py http://127.0.0.1:8014 inputs.json

`inputs.json` maps fully namespaced input ids to values (a list becomes a tuple / range,
"id:shiny.action" for action buttons). Prints each output id with OK / the error text.
"""
import asyncio
import json
import re
import sys

import requests
import websockets

OUTPUT_ID_RE = re.compile(r'<[^>]+class="[^"]*shiny-(?:html|text|data-frame)-output[^"]*"[^>]*\bid="([^"]+)"|'
                          r'<[^>]+\bid="([^"]+)"[^>]*class="[^"]*shiny-(?:html|text)-output[^"]*"|'
                          r'<shiny-data-frame id="([^"]+)"')


def output_ids(base_url: str) -> list[str]:
    html = requests.get(base_url, timeout=60).text
    ids = [a or b or c for a, b, c in OUTPUT_ID_RE.findall(html)]
    return sorted(set(ids))


async def run(base_url: str, inputs: dict, timeout: float = 120.0) -> int:
    outputs = output_ids(base_url)
    data = {**inputs, **{f".clientdata_output_{o}_hidden": False for o in outputs},
            ".clientdata_url_search": "", ".clientdata_pixelratio": 1}
    ws_url = base_url.replace("http", "ws", 1).rstrip("/") + "/websocket/"
    seen, errors = {}, {}
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.recv()                                        # config
        await ws.send(json.dumps({"method": "init", "data": data}))
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while len(seen) < len(outputs) and loop.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - loop.time())))
            except asyncio.TimeoutError:
                break
            for k, v in msg.get("values", {}).items():
                seen[k] = v
            for k, v in msg.get("errors", {}).items():
                seen[k] = None
                errors[k] = v.get("message") if isinstance(v, dict) else v
    missing = [o for o in outputs if o not in seen]
    for o in outputs:
        status = f"ERROR  {errors[o]}" if o in errors else ("MISSING (never rendered)" if o in missing else "OK")
        print(f"  {o:40s} {status}")
    print(f"{len(outputs) - len(errors) - len(missing)} ok, {len(errors)} errors, {len(missing)} missing")
    return 1 if errors or missing else 0


if __name__ == "__main__":
    base, path = sys.argv[1], sys.argv[2]
    sys.exit(asyncio.run(run(base, json.load(open(path)))))
