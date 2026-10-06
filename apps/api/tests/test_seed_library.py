"""The fictional seed library: eleven books that exercise every access class (ADR-0001 D15)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jdhp_api.core.orm import AccessClass, AgentRole, CollectionKind
from jdhp_api.modules.catalog.schemas import WorkCreate
from jdhp_api.modules.ingest.schemas import IntakeManifest
from jdhp_api.seed.generate import generate_isolated, staging_prefix_for
from jdhp_api.seed.loader import MAIN_SLUG, find_book, load_all, load_book, load_library

DIACRITICS = re.compile(r"[ً-ْٰ]")
FACETS = {"subject", "place", "period", "material"}


def plain(text: str) -> str:
    return DIACRITICS.sub("", text)


def lines_of(slug: str) -> list[str]:
    return [line for page in find_book(slug).pages for line in page.text_lines()]


def test_the_library_holds_the_seed_book_and_ten_short_books() -> None:
    books = load_all()
    assert books[0][0] == MAIN_SLUG
    assert books[0][1] is load_book()
    assert len(load_library()) == 10
    slugs = [slug for slug, _ in books]
    assert len(set(slugs)) == len(slugs)
    assert all(6 <= len(book.pages) <= 8 for _, book in load_library())


def test_every_access_class_has_a_book_and_classes_are_spread() -> None:
    classes = [book.work.access_class for _, book in load_all()]
    assert set(classes) == {c.value for c in AccessClass}
    assert classes.count("embargoed") == 1
    assert classes.count("restricted") >= 2
    assert classes.count("paid") >= 2
    assert classes.count("open") >= 2


def test_every_book_is_marked_fictional_and_validates_for_intake() -> None:
    for slug, book in load_all():
        assert "invented" in book.fictional_notice or "fiction" in book.fictional_notice.lower()
        assert "خيال" in (book.work.description_ar or "") or "خيال" in (book.item.provenance or "")
        WorkCreate.model_validate(book.work.work_create_fields())
        assert [page.seq for page in book.pages] == list(range(1, len(book.pages) + 1)), slug
        assert all(page.text_lines() for page in book.pages if page.type != "blank"), slug


def test_agent_roles_and_collection_kinds_are_ones_the_catalogue_knows() -> None:
    """Registration maps these onto enums; an unknown value would fail halfway through the seed."""
    for slug, book in load_all():
        for agent in book.work.agents:
            assert agent.role in {r.value for r in AgentRole}, (slug, agent.role)
        assert book.work.collection.kind in {k.value for k in CollectionKind}, slug


def test_shelfmarks_are_unique_and_sequential() -> None:
    marks = [book.item.shelfmark for _, book in load_all()]
    assert len(set(marks)) == len(marks)
    assert marks == [f"JDHP-SEED-{n:04d}" for n in range(1, len(marks) + 1)]


def test_catalogue_facets_cover_ten_governorates_and_several_periods_and_materials() -> None:
    places, periods, materials, subjects = set(), set(), set(), set()
    for slug, book in load_all():
        facets = {term.facet for term in book.work.terms}
        assert facets >= FACETS, (slug, facets)
        for term in book.work.terms:
            if term.facet == "place" and "خيال" not in term.label_ar:
                places.add(term.code)
            elif term.facet == "period":
                periods.add(term.code)
            elif term.facet == "material":
                materials.add(term.code)
            elif term.facet == "subject":
                subjects.add(term.code)
    assert len(places) >= 10, sorted(places)
    assert len(periods) >= 5, sorted(periods)
    assert len(materials) >= 7, sorted(materials)
    assert len(subjects) >= 12, sorted(subjects)


def test_books_share_three_collections() -> None:
    collections = {(b.work.collection.kind, b.work.collection.title_ar) for _, b in load_all()}
    assert len(collections) == 3
    assert {kind for kind, _ in collections} == {"project", "donor", "series"}


def test_only_the_seed_book_names_its_town_so_tests_can_find_it() -> None:
    """CI and the end-to-end suite search for the town; the other books must not match."""
    assert any("سميرة" in plain(line) for line in lines_of(MAIN_SLUG))
    for slug, _ in load_library():
        assert not any("سميرة" in plain(line) for line in lines_of(slug)), slug


def test_only_the_embargoed_book_names_jerash() -> None:
    """The public search for Jerash must come back empty, which proves the embargo (CAT-5)."""
    naming = [
        slug
        for slug, book in load_all()
        if any("جرش" in plain(line) for line in lines_of(slug))
        or any("جرش" in plain(term.label_ar) for term in book.work.terms)
    ]
    assert naming == ["10-mudhakkirat-muallim-fi-jarash"]
    assert find_book(naming[0]).work.access_class == "embargoed"


LINE_LIMITS = {"display": 40, "heading": 50, "center": 66, "body": 66, "caption": 80, "figure": 60}


def test_lines_fit_the_rendered_page() -> None:
    """The renderer does not wrap: each block kind has a width its font can hold."""
    for slug, book in load_all():
        for page in book.pages:
            for block in page.blocks:
                limit = LINE_LIMITS.get(block.kind, 66)
                for line in block.lines:
                    assert len(line) <= limit, (slug, page.seq, block.kind, line)


def test_staging_prefixes_are_distinct_per_book() -> None:
    prefixes = [staging_prefix_for(slug) for slug, _ in load_all()]
    assert prefixes[0] == "intake/seed-book"
    assert len(set(prefixes)) == len(prefixes)
    for prefix in prefixes:
        IntakeManifest.model_validate(
            {
                "new_work": {"title_ar": "x"},
                "capture": {"device": "d", "captured_on": "2026-09-01"},
                "staging_prefix": prefix,
                "pages": [{"seq": 1, "filename": "0001.tif", "sha256": "0" * 64}],
            }
        )


def test_find_book_refuses_an_unknown_slug() -> None:
    with pytest.raises(KeyError):
        find_book("not-a-book")


def test_a_library_book_renders_with_its_own_manifest(tmp_path: Path) -> None:
    """Rendered in a fresh interpreter like every caller: Pillow and libvips share no process."""
    slug = "04-kitab-al-aashab-wa-al-tibb"
    out = generate_isolated(tmp_path, scale=0.15, book=slug)
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    assert manifest["staging_prefix"] == f"intake/seed-{slug}"
    assert manifest["new_work"]["access_class"] == "registered"
    assert len(manifest["pages"]) == len(find_book(slug).pages)
    assert sorted(p.name for p in (out / "master").glob("*.tif")) == [
        f"{n:04d}.tif" for n in range(1, len(manifest["pages"]) + 1)
    ]
    truth = json.loads((out / "ground_truth" / "0003.json").read_text("utf-8"))
    assert truth["rtl"] is True
    assert truth["lines"]
