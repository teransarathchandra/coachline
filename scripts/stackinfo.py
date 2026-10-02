"""stackinfo.py - what a project is built with, read from its manifest files on this machine.

Only well-known public framework and library names and their major versions leave the machine (the research pass gets them):
never code, paths, the project name, or any other package. A company's own packages are usually unscoped and named after it,
so nothing outside the KNOWN list (or a known public npm scope) is sent, and local / workspace / git / url / private-registry
dependencies never are.
"""
import json, os, re

MAX = 12
MANIFESTS = ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml")
PUBLIC_SCOPES = {"@angular", "@vue", "@sveltejs", "@nestjs", "@remix-run", "@tanstack", "@prisma", "@supabase", "@trpc", "@mui",
                 "@radix-ui", "@reduxjs", "@apollo", "@playwright", "@storybook", "@astrojs", "@nuxt", "@vercel", "@aws-sdk",
                 "@google-cloud", "@anthropic-ai", "@testing-library", "@emotion", "@chakra-ui", "@headlessui", "@vitejs"}
KNOWN = set("""
react react-dom next vue nuxt svelte solid-js preact astro gatsby qwik lit ember-source express fastify koa hono typescript vite
webpack esbuild rollup parcel turbo tailwindcss bootstrap sass less styled-components framer-motion motion three d3 chart.js
recharts echarts redux zustand mobx jotai recoil pinia vuex react-router react-router-dom react-hook-form formik zod yup axios swr
graphql prisma drizzle-orm typeorm sequelize mongoose mongodb pg mysql2 redis ioredis socket.io electron react-native expo jest
vitest mocha cypress playwright puppeteer eslint prettier storybook lodash dayjs date-fns moment i18next next-auth firebase stripe
openai langchain ai lucide-react antd jquery htmx.org alpinejs remix
django flask fastapi starlette pydantic sqlalchemy alembic celery requests httpx aiohttp numpy pandas polars scipy scikit-learn
matplotlib seaborn plotly torch tensorflow keras jax transformers anthropic pytest psycopg psycopg2 psycopg2-binary asyncpg boto3
streamlit gradio uvicorn gunicorn jinja2 click typer rich scrapy beautifulsoup4 selenium djangorestframework channels flask-sqlalchemy
tokio serde serde_json axum actix-web rocket warp hyper reqwest clap anyhow thiserror sqlx diesel tracing rayon bevy tauri leptos
yew wasm-bindgen
""".split())
LOCAL = re.compile(r"^\s*[\"']?(file:|link:|workspace:|portal:|git|github:|https?:|\.|/|~/)", re.I)   # '~/' is a path, '~5.2' a range
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}$")
REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[=<>~!^]=?\s*([0-9][^\s,;]*))?")
SECTION = r"(?ms)^\[{}\]\s*$(.*?)(?=^\[|\Z)"


def _entry(name, spec=""):
    """'name@major', 'name', or None when this dependency must not leave the machine."""
    name, spec = str(name).strip().lower(), str(spec)
    if LOCAL.match(spec): return None
    if name.startswith("@"):
        scope, _, rest = name.partition("/")
        if scope not in PUBLIC_SCOPES or not NAME.match(rest): return None
    elif name not in KNOWN: return None
    m = re.search(r"\d+", spec)
    return f"{name}@{m.group(0)}" if m else name


def _text(path):
    with open(path, encoding="utf-8", errors="ignore") as f: return f.read(200_000)


def _npm(d):
    try: j = json.loads(_text(os.path.join(d, "package.json")))
    except ValueError: return []
    out = []
    for sec in ("dependencies", "devDependencies"):                  # what the app runs on first
        deps = j.get(sec) if isinstance(j, dict) else None
        for n, v in (deps.items() if isinstance(deps, dict) else []):
            if not str(n).startswith("@types/"): out.append(_entry(n, v))
    return ["node"] + out


def _req(line):
    line = line.split("#")[0].strip()
    if not line or line.startswith(("-", ".", "/")) or "://" in line or " @ " in line: return None
    m = REQ.match(line)
    return _entry(m.group(1), m.group(2) or "") if m else None


def _python(d, found):
    out = []
    if "pyproject.toml" in found:
        t = _text(os.path.join(d, "pyproject.toml"))
        m = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]\s*$", t)          # the closing ']' ends a line; 'psycopg[binary]' does not
        if m: out += [_req(s) for s in re.findall(r"[\"']([^\"']+)[\"']", m.group(1))]
        p = re.search(SECTION.format(r"tool\.poetry\.dependencies"), t)
        for n, rest in re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=\s*(.+)$", p.group(1) if p else ""):
            if n.lower() != "python" and not re.search(r"\b(path|git|url)\s*=", rest): out.append(_entry(n, rest))
    if "requirements.txt" in found:
        out += [_req(l) for l in _text(os.path.join(d, "requirements.txt")).splitlines()]
    return ["python"] + out


def _go(d):
    m = re.search(r"(?m)^go\s+(\d+\.\d+)", _text(os.path.join(d, "go.mod")))
    return ["go@" + m.group(1)] if m else ["go"]               # module paths are often private: only the language goes


def _rust(d):
    m = re.search(SECTION.format("dependencies"), _text(os.path.join(d, "Cargo.toml")))
    out = [_entry(n, rest.replace("version", "")) for n, rest in re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_-]*)\s*=\s*(.+)$", m.group(1) if m else "")
           if not re.search(r"\b(path|git|registry)\s*=", rest)]
    return ["rust"] + out


def _read(d, found):
    out = []
    if "package.json" in found: out += _npm(d)
    if "pyproject.toml" in found or "requirements.txt" in found: out += _python(d, found)
    if "go.mod" in found: out += _go(d)
    if "Cargo.toml" in found: out += _rust(d)
    seen, clean = set(), []
    for e in out:
        if e and e not in seen: seen.add(e); clean.append(e)
    return clean


def detect(project):
    """['node', 'next@15', 'react@19', ...] for the folder a prompt was typed in; [] when there is nothing to read. Never raises."""
    try:
        d = os.path.abspath(project) if project else ""
        for _ in range(5):
            if not d or not os.path.isdir(d): return []
            found = [m for m in MANIFESTS if os.path.isfile(os.path.join(d, m))]
            if found: return _read(d, found)[:MAX]
            up = os.path.dirname(d)
            if os.path.isdir(os.path.join(d, ".git")) or up == d: return []
            d = up
        return []
    except (OSError, ValueError, TypeError, AttributeError):
        return []
