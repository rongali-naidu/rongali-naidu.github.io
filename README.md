# rongali-naidu.github.io

Source for https://rongali-naidu.github.io. Posts come from the
[blogs](https://github.com/rongali-naidu/blogs) repo; only posts with `publish: true`
in their front matter are shown.

## How it updates

The GitHub Actions workflow in `.github/workflows/deploy.yml` builds and deploys the site:

- on every push to this repo,
- every 3 hours (to pick up new or edited posts in `blogs`),
- or on demand: **Actions → Build and deploy → Run workflow**.

## Editing

- `site.yaml`: name, tagline, links, and the About page text.
- `templates/`: page layouts (Jinja2).
- `static/`: CSS and JavaScript.

## Building locally

```bash
pip install -r requirements.txt
git clone https://github.com/rongali-naidu/blogs ../blogs
python build.py --content ../blogs --out dist
python serve.py 4000
```
