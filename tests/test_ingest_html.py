"""Scraped pages arrive wrapped in their navigation.

`read_document`'s own docstring said so long before anything was done about it.
PyMuPDF lays HTML out into pages with script and style dropped, which is why no
HTML parser was needed — but it keeps the nav, the sidebars and the footer, and
flattens them into the text a lesson may quote.

Measured on /srv/recall/corpus/CSE326/u3-mdn-box-model.html, a real file: 222,277
bytes become 77,160 (65% of that page was chrome) and 34 laid-out pages become
20. The first candidate a writer is offered goes from MDN's mega-menu to "The box
model Everything in CSS has a box around it, and understanding these boxes is key
to being able to create more complex layouts with CSS…" — the sentence a unit 3
lesson would obviously cite, which could not previously be quoted clean.
"""

from recall.ingest.pdf import strip_html_chrome

# The shape MDN and the WHATWG spec actually use.
PAGE = b"""<!doctype html><html><head><title>The box model</title></head><body>
<a class="skip-link" href="#content">Skip to main content</a>
<header class="page-layout__header"><nav class="menu"><ul>
<li>HTML</li><li>CSS</li><li>JavaScript</li><li>See all&hellip;</li></ul></nav></header>
<aside class="layout__left-sidebar" id="main-sidebar"><nav class="left-sidebar"><ol>
<li>1. Intro</li><li>2. Boxes</li><li>3. Overflow</li></ol></nav></aside>
<main id="content"><h1>The box model</h1>
<p>Everything in CSS has a box around it.</p>
<pre>if (a &amp;lt; b) { return a &amp; b; }</pre></main>
<aside class="reference-layout__toc"><ol><li>4. See also</li></ol></aside>
<footer class="footer"><p>Content available under a Creative Commons license.</p></footer>
</body></html>"""


def test_the_nav_sidebars_and_footer_go_and_the_article_stays():
    out = strip_html_chrome(PAGE).decode()
    for gone in ("<nav", "<aside", "<footer", "See all", "Intro", "Overflow",
                 "See also", "Creative Commons"):
        assert gone not in out, gone
    assert "Everything in CSS has a box around it." in out
    assert "<h1>The box model</h1>" in out


def test_keeping_only_main_would_have_emptied_the_spec_pages():
    """The tempting shortcut, and why it is not taken: the WHATWG Living Standard
    pages have no <main> at all, so "keep only <main>" returns nothing for 17 of
    CSE326's files. Chrome is removed by NAME instead."""
    whatwg = (b"<html><body><header id=head><h1>HTML Standard</h1></header>"
              b"<nav><a href='#x'>1 Introduction</a></nav>"
              b"<p>The title attribute represents advisory information.</p>"
              b"</body></html>")
    out = strip_html_chrome(whatwg).decode()
    assert "The title attribute represents advisory information." in out
    assert "1 Introduction" not in out
    assert "HTML Standard" not in out  # it was inside <header>


def test_entities_survive_verbatim_because_one_decode_is_already_too_many():
    """`convert_charrefs=False` is load-bearing, not a detail.

    With the default, `handle_data` receives DECODED text, so re-emitting it would
    silently undo one level of escaping — and that is the bug that made an MDN
    page teach that the character reference for "<" is "<". A page writes
    `&amp;lt;` in order to DISPLAY `&lt;`, and both levels have to come through."""
    out = strip_html_chrome(PAGE).decode()
    assert "a &amp;lt; b" in out
    assert "return a &amp; b" in out


def test_an_unclosed_chrome_tag_falls_back_rather_than_eating_the_article():
    """The one way this parser can lose real content, and scraped HTML is exactly
    where a missing close tag lives. Detected exactly — the document ended inside
    a dropped subtree — rather than guessed at from the output's size."""
    broken = (b"<html><body><nav><ul><li>menu</li></ul>"
              b"<main><p>The real article survives.</p></main></body></html>")
    assert strip_html_chrome(broken) == broken


def test_a_share_based_guard_would_have_disabled_the_strip():
    """Why the size floor is 5% and not something that looks more sensible.

    On this page chrome IS most of the markup — 65% of the real MDN file — so any
    floor near a plausible-looking value silently turns the whole strip off on the
    pages that need it most. That was tried: a 40% floor left this fixture
    completely unchanged."""
    out = strip_html_chrome(PAGE)
    assert len(out) < 0.75 * len(PAGE), "the strip did nothing"


def test_the_same_tag_nested_inside_itself_closes_in_the_right_place():
    nested = b"<html><body><nav>a<div><nav>b</nav></div>c</nav><p>kept</p></body></html>"
    out = strip_html_chrome(nested).decode()
    assert "kept" in out
    for gone in ("a", "b", "c"):
        assert ">%s<" % gone not in out


def test_a_pdf_is_not_touched_by_any_of_this():
    """Only markup formats are re-parsed. A PDF goes to PyMuPDF as a path, exactly
    as before, so nothing in the mathematics corpora changes."""
    import inspect

    from recall.ingest import pdf

    source = inspect.getsource(pdf.read_document)
    assert "_MARKUP_SUFFIXES" in source
    assert ".pdf" not in str(pdf._MARKUP_SUFFIXES)
