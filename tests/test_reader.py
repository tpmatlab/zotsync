from zotsync.reader import (
    build_collection_paths, normalize_doi, normalize_items, parse_year,
)

COLLS = [
    {"key": "C1", "data": {"name": "Review cimento", "parentCollection": False}},
    {"key": "C2", "data": {"name": "Fissuração", "parentCollection": "C1"}},
]

ITEMS = [
    {"key": "A1", "data": {
        "key": "A1", "version": 5, "itemType": "journalArticle",
        "title": "Cracking of cement paste", "date": "2021-03-15",
        "DOI": "https://doi.org/10.1016/J.CEMCONRES.2021.106000",
        "publicationTitle": "Cement and Concrete Research",
        "creators": [{"creatorType": "author", "firstName": "Ana", "lastName": "Silva"},
                     {"creatorType": "author", "name": "Instituto X"}],
        "tags": [{"tag": "shrinkage"}, {"tag": "shrinkage"}],
        "collections": ["C2"], "dateModified": "2024-01-01T00:00:00Z"}},
    {"key": "P1", "data": {"key": "P1", "itemType": "attachment", "parentItem": "A1",
                            "contentType": "application/pdf"}},
    {"key": "N1", "data": {"key": "N1", "itemType": "note", "parentItem": "A1"}},
    {"key": "B2", "data": {"key": "B2", "itemType": "preprint", "title": "Sem DOI campo",
                            "date": "n.d. 2019", "extra": "DOI: 10.1234/abc.def.",
                            "creators": [], "collections": []}},
    {"key": "D3", "data": {"key": "D3", "itemType": "journalArticle", "title": "Lixeira",
                            "deleted": 1}},
]


def test_normalize_doi():
    assert normalize_doi("doi:10.1016/J.X.2021.1") == "10.1016/j.x.2021.1"
    assert normalize_doi("https://doi.org/10.1016/ABC).") == "10.1016/abc"  # trailing punctuation removed
    # legitimate trailing parenthesis is kept; stray one is removed
    assert normalize_doi("10.1061/(ASCE)0733-9399(1994)120:12(2519)") == "10.1061/(asce)0733-9399(1994)120:12(2519)"
    assert normalize_doi("(veja 10.1016/j.x.2021.1)") == "10.1016/j.x.2021.1"
    # formatos reais vistos no Notion
    assert normalize_doi("doi.org/10.1016/S1876-3804(20)60102-1") == "10.1016/s1876-3804(20)60102-1"
    assert normalize_doi("doi.org/ 10.1680/jmacr.16.00394") == "10.1680/jmacr.16.00394"
    assert normalize_doi("doi.org/10.1016/j.conbuildmat.2021.125778?utm_source=chatgpt.com") == "10.1016/j.conbuildmat.2021.125778"
    assert normalize_doi("http://dx.doi.org/10.1016/j.compositesb.2015.11.007") == "10.1016/j.compositesb.2015.11.007"
    assert normalize_doi("https://ascelibrary.org/doi/10.1061/%28ASCE%29MT.1943-5533.0003082") == "10.1061/(asce)mt.1943-5533.0003082"
    assert normalize_doi("10.1007/978-0-387-78747-3") == "10.1007/978-0-387-78747-3"
    assert normalize_doi("https://drive.google.com/drive/folders/1U1bqvSXCUZdVThuJzccChVBxddbr0WNA") == ""
    assert normalize_doi("sem doi") == ""
    assert normalize_doi(None) == ""


def test_parse_year():
    assert parse_year("2021-03-15") == 2021
    assert parse_year("March 2019") == 2019
    assert parse_year("") is None


def test_collection_paths():
    assert build_collection_paths(COLLS) == {"C1": "Review cimento", "C2": "Review cimento / Fissuração"}


def test_normalize_items():
    refs = {r.key: r for r in normalize_items(ITEMS, build_collection_paths(COLLS), 999)}
    assert set(refs) == {"A1", "B2"}          # anexo, nota e lixeira ficam de fora
    a = refs["A1"]
    assert a.doi == "10.1016/j.cemconres.2021.106000"
    assert a.authors == ["Silva, Ana", "Instituto X"]
    assert a.year == 2021 and a.has_pdf
    assert a.tags == ["shrinkage"]
    assert a.collections == ["Review cimento / Fissuração"]
    assert a.zotero_uri == "zotero://select/groups/999/items/A1"
    b = refs["B2"]
    assert b.doi == "10.1234/abc.def" and not b.has_pdf and b.year == 2019
