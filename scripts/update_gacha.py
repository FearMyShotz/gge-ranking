import argparse
import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = "gge-services/client-source"
SOURCES = {
    "highscore": "bundles/ggs.dll/modules/exports/HighscoreConst.js",
    "event": "bundles/ggs.dll/modules/exports/EventConst.js",
}


def request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gge-ranking-sync/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(attempt + 1)
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def load_client(root=None):
    if root:
        return "local", {key: (pathlib.Path(root) / path).read_text(encoding="utf-8") for key, path in SOURCES.items()}
    sha = json.loads(request(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
    if not re.fullmatch("[a-f0-9]{40}", sha):
        raise ValueError("Invalid client-source revision")
    return sha, {key: request(f"https://raw.githubusercontent.com/{REPO}/{sha}/{path}").decode("utf-8") for key, path in SOURCES.items()}



def load_official_client():
    base = "https://empire-html5.goodgamestudios.com/default/"
    html = request(base + "index.html?inGameShop=1&allowFullScreen=true").decode("utf-8")
    match = re.search(r'<link\b(?=[^>]*\brel=["\']preload["\'])(?=[^>]*\bas=["\']script["\'])[^>]*\bhref=["\'](dll/ggs\.dll\.[a-f0-9]+\.js)["\']', html, re.I)
    if not match:
        raise ValueError("Official client DLL preload not found")
    asset = base + match.group(1)
    body = request(asset)
    if len(body) < 100000:
        raise ValueError("Official client DLL is unexpectedly small")
    raw = body.decode("utf-8")
    return hashlib.sha256(body).hexdigest(), asset, {"highscore": raw, "event": raw}


def parse_client(sources):
    scores = {name.removesuffix("_EVENT"): int(value) for name, value in re.findall(r"\b[A-Za-z_$][A-Za-z0-9_$]*\.([A-Z][A-Z0-9_]*_GACHA_EVENT)\s*=\s*(\d+)(?=[,;])", sources["highscore"])}
    events = {name: int(value) for name, value in re.findall(r"\b[A-Za-z_$][A-Za-z0-9_$]*\.EVENTTYPE_([A-Z][A-Z0-9_]*_GACHA)\s*=\s*(\d+)(?=[,;])", sources["event"])}
    if len(scores) < 8 or scores.keys() != events.keys():
        raise ValueError(f"Gacha enum mismatch: highscore={sorted(scores)}, event={sorted(events)}")
    if len(set(scores.values())) != len(scores) or len(set(events.values())) != len(events):
        raise ValueError("Duplicate Gacha identifiers")
    return [
        {"type": name, "eventId": events[name], "rankingId": scores[name],
         "key": "dialog_title_gachadeco2x2" if name == "DECO_GACHA" else f"event_title_{events[name]}"}
        for name in sorted(scores, key=lambda name: scores[name])
    ]


def probe(event, server):
    rank = event["rankingId"]
    payload = urllib.parse.quote(f'"LT":{rank},"LID":1,"SV":"1"', safe=":,")
    endpoint = f"https://empire-api.fly.dev/{urllib.parse.quote(server, safe='')}/hgh/{payload}"
    try:
        data = json.loads(request(endpoint))
    except urllib.error.HTTPError as error:
        if error.code == 400:
            return False
        raise
    content = data.get("content") or {}
    if str(data.get("return_code")) != "0":
        return False
    if int(content.get("LT", -1)) != rank:
        raise ValueError(f"Unexpected ranking type returned for {rank}")
    return isinstance(content.get("L"), list) and bool(content["L"]) and int(content.get("LR", 0)) > 0


def choose(mapping, available):
    candidates = [event for event in mapping if event["rankingId"] in available]
    seasonal = [event for event in candidates if event["type"] != "DECO_GACHA"]
    if len(seasonal) > 1:
        raise ValueError(f"Ambiguous seasonal Gacha rankings: {[x['rankingId'] for x in seasonal]}")
    if seasonal:
        return seasonal[0]
    deco = [event for event in candidates if event["type"] == "DECO_GACHA"]
    if deco:
        return deco[0]
    raise ValueError("No confirmed live Gacha; retaining previous selection")


def merge_events(data, mapping):
    result = json.loads(json.dumps(data))
    generated = {item["key"] for item in mapping}
    generated.update(key for key, value in data["player"].items() if value.get("gacha") is True)
    result["player"] = {key: value for key, value in data["player"].items() if key not in generated}
    for item in mapping:
        old = data["player"].get(item["key"], {})
        result["player"][item["key"]] = {
            **{key: value for key, value in old.items() if key not in ("id", "categories")},
            "id": item["rankingId"],
            "gacha": True,
            "categories": [{"id": 1, "name": "dialog_ci_filter01_all"}],
        }
    return result


def write_if_changed(path, data):
    value = json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != value:
        path.write_text(value, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-source-root")
    parser.add_argument("--server", default="EmpireEx_2")
    args = parser.parse_args()
    if args.client_source_root:
        sha, sources = load_client(args.client_source_root)
        asset = None
        source_commit = sha
        matches_source = True
    else:
        sha, asset, sources = load_official_client()
        source_commit = None
        matches_source = None
    mapping = parse_client(sources)
    if not args.client_source_root:
        try:
            source_commit, published = load_client()
            matches_source = parse_client(published) == mapping
        except (ValueError, OSError, KeyError, urllib.error.HTTPError) as error:
            print(f"Client-Source comparison unavailable: {error}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(lambda event: probe(event, args.server), mapping))
    available = {item["rankingId"] for item, valid in zip(mapping, checks) if valid}
    active = choose(mapping, available)
    path = ROOT / "events.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    updated = merge_events(current, mapping)
    if updated != current:
        write_if_changed(path, updated)
    manifest_path = ROOT / "active-gacha.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest = {"server": args.server, "officialClientSha256": sha,
                "officialClientAsset": asset, "clientSourceRepository": REPO,
                "clientSourceCommit": source_commit, "clientSourceMatchesOfficial": matches_source,
                "active": active, "availableRankingIds": sorted(available)}
    if any(existing.get(key) != value for key, value in manifest.items()):
        manifest["checkedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        write_if_changed(manifest_path, manifest)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
