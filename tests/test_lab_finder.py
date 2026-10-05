import csv
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lab_finder as lf  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.responses.pop(0)


def make_place(pid, name="Ege Diş Protez Laboratuvarı", district="Karşıyaka", province="İzmir",
               lat=38.46, lng=27.11, status="OPERATIONAL", **extra):
    place = {
        "id": pid,
        "displayName": {"text": name, "languageCode": "tr"},
        "formattedAddress": f"1234. Sk. No:5, 35590 {district}/{province}, Türkiye",
        "addressComponents": [
            {"longText": district, "shortText": district, "types": ["administrative_area_level_2", "political"]},
            {"longText": province, "shortText": province, "types": ["administrative_area_level_1", "political"]},
        ],
        "location": {"latitude": lat, "longitude": lng},
        "businessStatus": status,
    }
    place.update(extra)
    return place


def quiet():
    return redirect_stderr(io.StringIO())


class NormalizeTest(unittest.TestCase):
    def test_turkish_letters(self):
        self.assertEqual(lf.normalize("Karşıyaka"), "karsiyaka")
        self.assertEqual(lf.normalize("İZMİR"), "izmir")
        self.assertEqual(lf.normalize("Çiğli Ödemiş Güzelbahçe"), "cigli odemis guzelbahce")
        self.assertEqual(lf.normalize(None), "")


class ClassifyTest(unittest.TestCase):
    def test_dental_labs(self):
        for name in ["Ege Diş Protez Laboratuvarı", "Dentlab İzmir", "Dentlabs", "Zirkonyum Diş Teknisyeni",
                     "Porselen Dental Lab", "Kuzey CAD/CAM Merkezi", "Tıbbi Diş Protez Lab",
                     "Dt. Mehmet Kaya Diş Protez Laboratuvarı", "Ege Zirkonyum"]:
            self.assertTrue(lf.is_likely_lab(name), name)

    def test_not_labs(self):
        for name in ["Karşıyaka Ağız ve Diş Sağlığı Polikliniği", "Dr. Ayşe Yılmaz Diş Hekimi",
                     "Özel Tıbbi Tahlil Laboratuvarı", "Ege Gıda Analiz Laboratuvarı",
                     "Ege Protez Ortez Laboratuvarı", "Protez Saç Merkezi", "Optik Laboratuvarı",
                     "Zirkonyum Diş Kliniği", "Dt. Ali Zirkonyum Diş Polikliniği", "Kalabak Diş Polikliniği",
                     "Ege Seramik Banyo", "Smile Zirkonyum Dental Clinic", "Ege Zirkonyum Dental Center",
                     "Zirkon Ağız Diş Sağlığı Merkezi", "Zirkonyum ADSM", "Porselen Dentist Ayşe Kaya",
                     "Porselen Lamina Diş Merkezi", "Ege Ortoprotez", "Orto Protez Merkezi",
                     "Protez Saçlar İzmir", "Göz Protezi Merkezi"]:
            self.assertFalse(lf.is_likely_lab(name), name)


class AddressTest(unittest.TestCase):
    def test_district_from_components(self):
        self.assertEqual(lf.district_of(make_place("a", district="Bornova"), "Konak"), "Bornova")

    def test_district_from_address_fallback(self):
        place = {"formattedAddress": "Bostanlı, 1234. Sk. No:5, 35590 Karşıyaka/İzmir, Türkiye"}
        self.assertEqual(lf.district_of(place, "Konak"), "Karşıyaka")
        self.assertEqual(lf.district_of({}, "Konak"), "Konak")

    def test_is_in_izmir(self):
        self.assertTrue(lf.is_in_izmir(make_place("a")))
        self.assertFalse(lf.is_in_izmir(make_place("a", province="Manisa")))
        self.assertTrue(lf.is_in_izmir({"formattedAddress": "Konak/IZMIR, Türkiye"}))
        self.assertFalse(lf.is_in_izmir({"formattedAddress": "Yunusemre/Manisa, Türkiye"}))


class ClientTest(unittest.TestCase):
    def client(self, responses, **kwargs):
        session = FakeSession(responses)
        return lf.PlacesClient("KEY", session=session, sleep=lambda s: None, **kwargs), session

    def test_pagination_sends_token_and_headers(self):
        client, session = self.client([
            FakeResponse(200, {"places": [make_place("a")], "nextPageToken": "tok1"}),
            FakeResponse(200, {"places": [make_place("b")]}),
        ])
        places = client.search_text("diş protez laboratuvarı Karşıyaka İzmir")
        self.assertEqual([p["id"] for p in places], ["a", "b"])
        self.assertEqual(client.request_count, 2)
        first, second = session.calls
        self.assertEqual(first["headers"]["X-Goog-Api-Key"], "KEY")
        self.assertIn("nextPageToken", first["headers"]["X-Goog-FieldMask"])
        self.assertIn("places.pureServiceAreaBusiness", first["headers"]["X-Goog-FieldMask"])
        self.assertNotIn("pageToken", first["json"])
        self.assertIs(first["json"]["includePureServiceAreaBusinesses"], True)
        self.assertEqual(first["json"]["pageSize"], 20)
        self.assertEqual(second["json"]["pageToken"], "tok1")
        self.assertEqual({k: v for k, v in second["json"].items() if k != "pageToken"}, first["json"])

    def test_stops_after_max_pages(self):
        client, _ = self.client([FakeResponse(200, {"places": [make_place(str(i))], "nextPageToken": "t"})
                                 for i in range(5)])
        self.assertEqual(len(client.search_text("q")), lf.MAX_PAGES)

    def test_location_restriction(self):
        client, session = self.client([FakeResponse(200, {})])
        rect = lf._rect(38.0, 27.0, 38.5, 27.5)
        self.assertEqual(client.search_text("q", rect), [])
        self.assertEqual(session.calls[0]["json"]["locationRestriction"], {"rectangle": rect})

    def test_retries_on_429(self):
        sleeps = []
        session = FakeSession([
            FakeResponse(429, {"error": {"message": "quota"}}),
            FakeResponse(200, {"places": [make_place("a")]}),
        ])
        client = lf.PlacesClient("KEY", session=session, sleep=sleeps.append)
        self.assertEqual(len(client.search_text("q")), 1)
        self.assertEqual(sleeps, [2])

    def test_gives_up_after_retries(self):
        client, _ = self.client([FakeResponse(503, {"error": {"message": "down"}})] * (lf.MAX_RETRIES + 1))
        with self.assertRaisesRegex(lf.PlacesError, "down"):
            client.search_text("q")

    def test_no_retry_on_403(self):
        client, session = self.client([FakeResponse(403, {"error": {"message": "API key not valid"}})])
        with self.assertRaisesRegex(lf.PlacesError, "403.*API key not valid"):
            client.search_text("q")
        self.assertEqual(len(session.calls), 1)

    def test_invalid_json_is_places_error(self):
        client, _ = self.client([FakeResponse(200, ValueError("bad json"))])
        with self.assertRaises(lf.PlacesError):
            client.search_text("q")

    def test_call_limit(self):
        client, session = self.client(
            [FakeResponse(200, {"places": [make_place(str(i))], "nextPageToken": "t"}) for i in range(3)],
            max_calls=2,
        )
        with self.assertRaisesRegex(lf.CallLimitReached, "--max-calls"):
            client.search_text("q")
        self.assertEqual(len(session.calls), 2)

    def test_district_viewport_picks_district_and_caches(self):
        district_box = {"low": {"latitude": 38.43, "longitude": 27.05},
                        "high": {"latitude": 38.52, "longitude": 27.20}}
        client, session = self.client([FakeResponse(200, {"places": [
            {"id": "street", "types": ["route"], "viewport": lf._rect(38.45, 27.1, 38.46, 27.11)},
            {"id": "district", "types": ["administrative_area_level_2", "political"], "viewport": district_box},
        ]})])
        self.assertEqual(client.district_viewport("Karşıyaka"), district_box)
        self.assertEqual(client.district_viewport("Karşıyaka"), district_box)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["json"]["textQuery"], "Karşıyaka, İzmir")
        self.assertEqual(session.calls[0]["headers"]["X-Goog-FieldMask"], lf.VIEWPORT_FIELD_MASK)

    def test_district_viewport_missing(self):
        client, _ = self.client([FakeResponse(200, {"places": [{"id": "x", "types": ["route"]}]})])
        self.assertIsNone(client.district_viewport("Kiraz"))


class FakeClient:
    """search_area testləri üçün: ərazisiz sorğuya 60 nəticə, bölünmüş ərazilərə 2 nəticə qaytarır."""

    def __init__(self, always_capped=False, viewport=None):
        self.calls = []
        self.always_capped = always_capped
        self.viewport = viewport
        self.viewport_requests = []

    def search_text(self, text_query, rect=None, sink=None):
        self.calls.append(rect)
        n = len(self.calls)
        if rect is None or self.always_capped:
            places = [make_place(f"{n}-{i}", lat=38.40 + i * 0.001, lng=27.10 + i * 0.001) for i in range(60)]
        else:
            places = [make_place(f"{n}-x"), make_place(f"{n}-y")]
        sink.extend(places)
        return places

    def district_viewport(self, district):
        self.viewport_requests.append(district)
        return self.viewport


class SearchAreaTest(unittest.TestCase):
    def test_splits_when_capped(self):
        client = FakeClient()
        places = lf.search_area(client, "q", "Karşıyaka")
        self.assertEqual(len(client.calls), 5)
        self.assertIsNone(client.calls[0])
        self.assertEqual(len(places), 60 + 4 * 2)
        lows = {(r["low"]["latitude"], r["low"]["longitude"]) for r in client.calls[1:]}
        self.assertEqual(len(lows), 4)

    def test_split_covers_whole_district(self):
        # Nəticələr ilçənin bir küncündə toplanıb; bölünmə bütün ilçəni əhatə etməlidir.
        district_box = lf._rect(38.30, 26.90, 38.70, 27.40)
        client = FakeClient(viewport=district_box)
        lf.search_area(client, "q", "Karşıyaka")
        self.assertEqual(client.viewport_requests, ["Karşıyaka"])
        self.assertEqual(lf.union_rect(*client.calls[1:]), district_box)

    def test_no_district_uses_results_box(self):
        client = FakeClient()
        lf.search_area(client, "q")
        self.assertEqual(client.viewport_requests, [])
        covered = lf.union_rect(*client.calls[1:])
        self.assertLessEqual(covered["low"]["latitude"], 38.40)
        self.assertGreaterEqual(covered["high"]["latitude"], 38.459)

    def test_depth_limit(self):
        client = FakeClient(always_capped=True)
        with quiet():
            lf.search_area(client, "q", "Karşıyaka")
        self.assertEqual(len(client.calls), 1 + 4 + 16)

    def test_capped_outside_izmir_warns(self):
        class OutsideClient(FakeClient):
            def search_text(self, text_query, rect=None, sink=None):
                self.calls.append(rect)
                places = [make_place(str(i), province="Manisa") for i in range(60)]
                sink.extend(places)
                return places

        client = OutsideClient()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(len(lf.search_area(client, "q", "Kınık")), 60)
        self.assertIn("xəbərdarlıq", err.getvalue())
        self.assertEqual(len(client.calls), 1)

    def test_interrupted_split_keeps_fetched_results(self):
        class StopClient(FakeClient):
            def search_text(self, text_query, rect=None, sink=None):
                if len(self.calls) == 3:
                    raise lf.CallLimitReached("limit")
                return super().search_text(text_query, rect, sink)

        sink = []
        with self.assertRaises(lf.CallLimitReached):
            lf.search_area(StopClient(), "q", "Karşıyaka", sink=sink)
        self.assertEqual(len(sink), 60 + 2 * 2)

    def test_bounding_box_and_clamp(self):
        box = lf.bounding_box([make_place("a", lat=38.0, lng=27.0), make_place("b", lat=38.4, lng=27.4)])
        self.assertAlmostEqual(box["low"]["latitude"], 37.9)
        self.assertAlmostEqual(box["high"]["longitude"], 27.5)
        self.assertIsNone(lf.bounding_box([{"id": "x"}]))
        wide = lf._rect(36.0, 25.0, 41.0, 30.0)
        self.assertEqual(lf.clamp_to_izmir(wide), lf._rect(*lf.IZMIR_BOUNDS["low"], *lf.IZMIR_BOUNDS["high"]))
        self.assertIsNone(lf.clamp_to_izmir(lf._rect(40.0, 29.0, 41.0, 30.0)))
        self.assertIsNone(lf.clamp_to_izmir(None))

    def test_split_rect(self):
        quads = lf.split_rect(lf._rect(38.0, 27.0, 39.0, 28.0))
        self.assertEqual(quads[0], lf._rect(38.0, 27.0, 38.5, 27.5))
        self.assertEqual(quads[3], lf._rect(38.5, 27.5, 39.0, 28.0))


RESPONSES = {
    "diş protez laboratuvarı Karşıyaka İzmir": [
        make_place("lab1", nationalPhoneNumber="0232 111 11 11", websiteUri="https://ege.example",
                   googleMapsUri="https://maps.google.com/?cid=1", rating=4.8, userRatingCount=12),
        make_place("clinic", name="Karşıyaka Ağız ve Diş Sağlığı Polikliniği",
                   primaryTypeDisplayName={"text": "Diş Hekimi"}),
        make_place("closed", name="Eski Protez Lab", status="CLOSED_PERMANENTLY"),
        make_place("manisa", name="Manisa Dental Lab", district="Yunusemre", province="Manisa"),
        {"id": "sab", "displayName": {"text": "Mobil Diş Teknisyeni"}, "pureServiceAreaBusiness": True,
         "businessStatus": "OPERATIONAL"},
    ],
    "dental laboratuvar Karşıyaka İzmir": [
        make_place("lab1"),
        make_place("lab2", name="Bostanlı Dental Lab", district="Çiğli", status="CLOSED_TEMPORARILY"),
    ],
}


class DictClient:
    def __init__(self, responses=RESPONSES, fail_on=None, exc=None):
        self.responses = responses
        self.fail_on = fail_on
        self.exc = exc
        self.request_count = 0

    def search_text(self, text_query, rect=None, sink=None):
        self.request_count += 1
        if text_query == self.fail_on:
            raise self.exc
        places = self.responses.get(text_query, [])
        sink.extend(places)
        return places


class CollectAndRowsTest(unittest.TestCase):
    def setUp(self):
        queries = lf.build_queries(["Karşıyaka"], ["diş protez laboratuvarı", "dental laboratuvar"])
        with quiet():
            self.records = lf.collect(DictClient(), queries, {})

    def test_dedup_and_keywords(self):
        self.assertEqual(set(self.records), {"lab1", "clinic", "closed", "manisa", "lab2", "sab"})
        self.assertEqual(list(self.records["lab1"]["keywords"]),
                         ["diş protez laboratuvarı", "dental laboratuvar"])

    def test_build_rows(self):
        labs, review, skipped = lf.build_rows(self.records)
        self.assertEqual([r["name"] for r in labs], ["Bostanlı Dental Lab", "Ege Diş Protez Laboratuvarı"])
        self.assertEqual([r["name"] for r in review],
                         ["Karşıyaka Ağız ve Diş Sağlığı Polikliniği", "Mobil Diş Teknisyeni"])
        self.assertEqual(skipped, {"closed": 1, "outside": 1})
        ege = labs[1]
        self.assertEqual(ege["phone"], "0232 111 11 11")
        self.assertEqual(ege["district"], "Karşıyaka")
        self.assertEqual(ege["keywords"], "diş protez laboratuvarı, dental laboratuvar")
        self.assertEqual(labs[0]["district"], "Çiğli")
        self.assertEqual(labs[0]["note"], "Müvəqqəti bağlı")
        self.assertEqual(review[0]["category"], "Diş Hekimi")
        self.assertEqual(review[1]["note"], "Ünvan gizlədilib (xidmət ərazisi)")
        self.assertEqual(review[1]["district"], "Karşıyaka")

    def test_write_files(self):
        labs, review, _ = lf.build_rows(self.records)
        labs[0]["address"] = "Bozuk\x01 adres"
        with tempfile.TemporaryDirectory() as tmp:
            xlsx, csv_path = Path(tmp, "out.xlsx"), Path(tmp, "out.csv")
            lf.write_xlsx(xlsx, labs, review)
            lf.write_csv(csv_path, labs, review)

            wb = load_workbook(xlsx)
            self.assertEqual(wb.sheetnames, ["Lablar", "Yoxlanmalı"])
            ws = wb["Lablar"]
            self.assertEqual(ws.cell(row=1, column=1).value, "Ad")
            self.assertEqual(ws.max_row, 3)
            self.assertEqual(ws.cell(row=2, column=3).value, "Bozuk adres")
            self.assertEqual(ws.cell(row=3, column=6).value, 4.8)
            self.assertEqual(ws.cell(row=3, column=8).hyperlink.target, "https://maps.google.com/?cid=1")
            self.assertEqual(wb["Yoxlanmalı"].max_row, 3)

            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0][:3], ["Növ", "Ad", "İlçə"])
            self.assertEqual([r[0] for r in rows[1:]], ["Lab", "Lab", "Yoxlanmalı", "Yoxlanmalı"])


class OutputTest(unittest.TestCase):
    def test_output_paths_keep_dots(self):
        csv_path, xlsx_path = lf.output_paths(Path("output/izmir_05.10.2026"))
        self.assertEqual((csv_path.name, xlsx_path.name), ("izmir_05.10.2026.csv", "izmir_05.10.2026.xlsx"))
        csv_path, xlsx_path = lf.output_paths(Path("output/izmir.xlsx"))
        self.assertEqual((csv_path.name, xlsx_path.name), ("izmir.csv", "izmir.xlsx"))

    def test_check_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = lf.output_paths(Path(tmp, "new", "out"))
            self.assertIsNone(lf.check_writable(paths))
            self.assertFalse(paths[0].exists())  # yoxlama boş fayl qoyub getmir
            Path(tmp, "busy.xlsx").mkdir()
            self.assertIn("busy.xlsx", lf.check_writable(lf.output_paths(Path(tmp, "busy"))))

    def test_save_outputs_falls_back_when_file_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "out.xlsx").mkdir()  # yazmaq olmayan "fayl"
            with quiet():
                saved = lf.save_outputs(Path(tmp, "out"), [], [])
            self.assertEqual(saved[0], Path(tmp, "out.csv"))
            self.assertRegex(saved[1].name, r"^out_\d{8}_\d{6}\.xlsx$")
            self.assertTrue(saved[1].is_file())


class MainTest(unittest.TestCase):
    def run_main(self, client, extra_args=()):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "KEY"}), \
                mock.patch.object(lf, "PlacesClient", lambda *a, **k: client):
            out = io.StringIO()
            with redirect_stdout(out), quiet():
                code = lf.main(["--districts", "Karşıyaka", "--output", str(Path(tmp, "res")), *extra_args])
            files = sorted(p.name for p in Path(tmp).iterdir())
        return code, out.getvalue(), files

    def test_full_run(self):
        code, out, files = self.run_main(DictClient())
        self.assertEqual(code, 0)
        self.assertEqual(files, ["res.csv", "res.xlsx"])
        self.assertIn("Cəmi: 2 lab", out)

    def test_ctrl_c_keeps_partial_results(self):
        client = DictClient(fail_on="diş laboratuvarı Karşıyaka İzmir", exc=KeyboardInterrupt())
        code, out, files = self.run_main(client)
        self.assertEqual(code, 1)
        self.assertEqual(files, ["res.csv", "res.xlsx"])
        self.assertIn("Cəmi: 2 lab", out)

    def test_call_limit_keeps_partial_results(self):
        client = DictClient(fail_on="dental laboratuvar Karşıyaka İzmir", exc=lf.CallLimitReached("limit"))
        code, _, files = self.run_main(client)
        self.assertEqual(code, 1)
        self.assertEqual(files, ["res.csv", "res.xlsx"])

    def test_failure_mid_first_query_keeps_fetched_pages(self):
        session = FakeSession([
            FakeResponse(200, {"places": [make_place("a"), make_place("b", name="Bornova Dental Lab")],
                               "nextPageToken": "t"}),
            FakeResponse(403, {"error": {"message": "billing disabled"}}),
        ])
        client = lf.PlacesClient("KEY", session=session, sleep=lambda s: None)
        code, out, files = self.run_main(client)
        self.assertEqual(code, 1)
        self.assertEqual(files, ["res.csv", "res.xlsx"])
        self.assertIn("Cəmi: 2 lab", out)
        self.assertIn("API çağırışı: 2", out)

    def test_error_before_any_result(self):
        client = DictClient(fail_on="diş protez laboratuvarı Karşıyaka İzmir", exc=lf.PlacesError("403"))
        code, out, files = self.run_main(client)
        self.assertEqual(code, 1)
        self.assertEqual(files, [])
        self.assertIn("API çağırışı: 1", out)


class CliTest(unittest.TestCase):
    def test_resolve_districts(self):
        self.assertEqual(lf.resolve_districts(["karsiyaka", "ÇİĞLİ", "Karşıyaka"]), ["Karşıyaka", "Çiğli"])
        self.assertEqual(len(lf.resolve_districts(None)), 30)
        with self.assertRaises(SystemExit):
            lf.resolve_districts(["Kadıköy"])

    def test_dry_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(lf.main(["--dry-run", "--districts", "Karşıyaka"]), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[:len(lf.KEYWORDS)], [f"{k} Karşıyaka İzmir" for k in lf.KEYWORDS])
        n = len(lf.KEYWORDS)
        self.assertTrue(lines[n + 1].startswith(f"{n} sorğu. Adətən {n}–{3 * n} API çağırışı"), lines[n + 1])
        self.assertIn(f"~{n * 63 + 1}", lines[n + 1])

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "  "}), quiet():
            self.assertEqual(lf.main(["--districts", "Karşıyaka"]), 1)

    def test_bad_output_name(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lf.parse_args(["--output", "."])

    def test_negative_max_calls(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lf.parse_args(["--max-calls", "-5"])


if __name__ == "__main__":
    unittest.main()
