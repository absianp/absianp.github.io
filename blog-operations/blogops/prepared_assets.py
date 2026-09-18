"""Attach three explicitly supplied, hash-verified local images without a model.

`before_heading` is the exact text after an ATX `##` marker, without the marker.
Missing headings and omitted hints append the corresponding figure at the end.
The input article and files are never modified.
"""
import copy
import hashlib
import html
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROLES = ("thumbnail", "body-1", "body-2")
_FIELDS = {"role", "url", "sha256", "alt", "caption", "before_heading", "provenance"}


def _noncode_lines(body):
    """Yield original offsets, excluding fenced Markdown examples."""
    offset, fence = 0, None
    for line in body.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*", text):
                fence = None
        else:
            opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", text)
            if opening and (opening[1][0] != "`" or "`" not in opening[2]):
                fence = (opening[1][0], len(opening[1]))
            else:
                yield offset, line
        offset += len(line)


def _reject_existing_images(body):
    prose = "".join(line for _, line in _noncode_lines(body))
    prose = re.sub(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", "", prose)
    # Includes Markdown inline/reference/shortcut images and native HTML/SVG.
    if re.search(r"!\[[^\]]*\]|<(?:img|picture|svg|image)\b", prose, re.I):
        raise ValueError("Article body already contains images; remove them explicitly before attaching supplied assets")


def _asset_path(public, url):
    if not isinstance(url, str) or not url.startswith("/images/") or re.search(r"[\s\x00-\x1f\x7f\\]", url):
        raise ValueError("Asset URL must be a local /images/ URL")
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or parsed.path != url:
        raise ValueError("External or noncanonical image URLs are not allowed")
    if re.search(r"%(?![0-9A-Fa-f]{2})", url):
        raise ValueError("Invalid image URL encoding")
    decoded = unquote(parsed.path, errors="strict")
    if not decoded.startswith("/images/") or re.search(r"[\x00-\x1f\x7f\\]", decoded):
        raise ValueError("Invalid image path")
    parts = decoded.lstrip("/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Image path cannot contain traversal or empty segments")
    path = (public / Path(*parts)).resolve()
    if not path.is_relative_to(public) or not path.is_file():
        raise ValueError("Supplied image is missing or escapes the public directory")
    return path


def _verified_assets(assets, public):
    if not isinstance(assets, list) or len(assets) != 3:
        raise ValueError("Exactly three image assets are required")
    by_role, seen_paths, seen_urls = {}, set(), set()
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) - _FIELDS:
            raise ValueError("Invalid supplied image record")
        role = asset.get("role")
        if role not in ROLES or role in by_role:
            raise ValueError("Each image role must occur exactly once")
        provenance = asset.get("provenance")
        if provenance not in ("reused", "generated"):
            raise ValueError("Image provenance must be reused or generated")
        expected = asset.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", expected):
            raise ValueError("Image SHA-256 must contain 64 hexadecimal characters")
        path = _asset_path(public, asset.get("url"))
        url = asset["url"]
        if url in seen_urls or path in seen_paths:
            raise ValueError("Image URLs and resolved files must be distinct")
        actual = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                actual.update(chunk)
        if actual.hexdigest() != expected.lower():
            raise ValueError("Supplied image SHA-256 does not match the complete file")
        clean = {"role": role, "url": url, "sha256": actual.hexdigest(), "provenance": provenance}
        if role != "thumbnail":
            for field in ("alt", "caption"):
                value = asset.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Body images require nonempty alt text and caption")
                clean[field] = value
            heading = asset.get("before_heading")
            if heading is not None:
                if not isinstance(heading, str) or not heading.strip() or "\n" in heading or "\r" in heading:
                    raise ValueError("before_heading must be one nonempty H2 text line")
                clean["before_heading"] = heading
        elif asset.get("before_heading") is not None:
            raise ValueError("The thumbnail cannot specify a body heading")
        by_role[role] = clean
        seen_urls.add(url)
        seen_paths.add(path)
    return [by_role[role] for role in ROLES]


def _headings(body):
    positions = {}
    for offset, line in _noncode_lines(body):
        match = re.match(r"^ {0,3}##[ \t]+(.+?)[ \t]*(?:\r?\n)?$", line)
        if match:
            text = re.sub(r"[ \t]+#+[ \t]*$", "", match[1]).strip()
            positions.setdefault(text, offset)
    return positions


def _figure(asset):
    role = asset["role"]
    return (f'<!-- provided-asset:{role} -->\n'
            f'<figure class="article-illustration" data-image-role="{role}">\n'
            f'<img src="{html.escape(asset["url"], quote=True)}" alt="{html.escape(asset["alt"], quote=True)}" loading="lazy" />\n'
            f'<figcaption>{html.escape(asset["caption"], quote=True)}</figcaption>\n'
            f'</figure>\n<!-- /provided-asset:{role} -->')


def attach_images(article, assets, root):
    """Return a new article using only the supplied, verified repository assets.

    Asset metadata is recorded as provided provenance. This function does not
    create `image_generation` or claim a native image-generation tool was run.
    Figures sharing a position always appear in body-1, body-2 order, regardless
    of the input list order. Explicit heading hints otherwise determine placement.
    """
    if not isinstance(article, dict) or not isinstance(article.get("markdown_content"), str) or not article["markdown_content"].strip():
        raise ValueError("Article must contain a nonempty Markdown body")
    body = article["markdown_content"]
    _reject_existing_images(body)
    repository = Path(root).resolve()
    public = (repository / "blog-frontend/public").resolve()
    if not public.is_relative_to(repository):
        raise ValueError("Public image directory escapes the repository")
    verified = _verified_assets(assets, public)
    headings = _headings(body)
    insertions = []
    for order, asset in enumerate(verified[1:]):
        position = headings.get(asset.get("before_heading"), len(body))
        insertions.append((position, order, _figure(asset)))
    chunks, cursor = [], 0
    for position, _, figure in sorted(insertions):
        chunks.append(body[cursor:position])
        chunks.append("\n\n" + figure + "\n\n")
        cursor = position
    chunks.append(body[cursor:])
    result = copy.deepcopy(article)
    for key in ("image_generation", "article_images", "heroImage"):
        result.pop(key, None)
    result["heroImage"] = verified[0]["url"]
    result["markdown_content"] = "".join(chunks)
    result["image_preparation"] = {"mode": "provided", "assets": verified}
    return result
