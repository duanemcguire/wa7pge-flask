# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static ham radio blog (WA7PGE) built with Flask + Flask-FlatPages + Frozen-Flask. Content is written as Markdown files with YAML frontmatter in `pages/`. The site is frozen to static HTML in `build/` and deployed to Netlify.

## Commands

All commands assume the virtualenv is activated (`source venv/bin/activate`).

**Dev server** (live preview at http://localhost:5002):
```
python sitebuilder.py
```

**Build static site** (outputs to `build/`):
```
python sitebuilder.py build
npx -y pagefind --site build   # rebuilds search index
```

**Deploy to Netlify**:
```
python sitebuilder.py build
cp _redirects build/_redirects
npx -y pagefind --site build
netlify deploy --prod --dir build
```

## Architecture

`sitebuilder.py` is the entire application — no separate modules.

- **Flask-FlatPages** reads all `.md` files from `pages/` and makes them available as page objects with `page.meta` (YAML frontmatter) and `page.html` (rendered body).
- **Frozen-Flask** crawls all routes and outputs static HTML to `build/`.
- **Pagefind** post-processes `build/` to generate a client-side search index.
- At startup, `sitebuilder.py` validates every page has a string `date` and string `title` in its frontmatter — bad values raise `ValueError` and prevent the server from starting.

## Page structure

Pages live under `pages/<Section>/` and map directly to URL paths. Sections: `Antennas`, `CW`, `Equipment`, `Main`, `POTA`, `Thoughts`, `Utilities`.

Required frontmatter fields for all pages:
```yaml
---
date: '2024-08-24T23:54:24'   # must be a string, not a bare YAML date
title: Page Title              # must be a string
---
```

POTA activation pages also require:
```yaml
spc: UT   # state/province code
```

Optional frontmatter:
- `img` — override the image used for OG/RSS (otherwise auto-detected from last image in body)
- `excrpt` — override the auto-generated excerpt
- `category` — list of category keys (used in `CATEGORY_DICT` in sitebuilder.py)
- `noindex: true` — adds `<meta name="robots" content="noindex">`

## POTA section

- `pages/POTA/Activations/` — parks the operator activated (one file per park, multiple activations per file)
- `pages/POTA/Hunted/<State>/` — parks hunted by state
- `static/POTA-Scenes/` — images for the `/POTA/Scenes/` gallery; image filenames starting with `US-NNNN` are auto-linked to their park page

## Templates

All templates extend `templates/base.html`. The base includes Bootstrap 4.2, Font Awesome 4.7, and the Pagefind search UI. The `breadcrumbs` variable is passed to every route and rendered as `{{breadcrumbs|safe}}`.

## External dependency

`lookup_park()` references a SQLite database at `~/docs/projects/Ham Radio/POTA/usa.db` (for park lookups by name when the filename doesn't contain a `US-NNNN` pattern). This is only used by the `/POTA/Scenes/` route.
