#!/usr/bin/env python3
"""İzmir diş protez laboratoriyalarını Google Places API (New) ilə tapır.

İstifadə:
    python lab_finder.py                                  # bütün İzmir
    python lab_finder.py --districts Karşıyaka Bornova    # seçilmiş ilçələr
    python lab_finder.py --dry-run                        # API-yə getmədən sorğuları göstər

API açarı GOOGLE_MAPS_API_KEY environment variable-dan oxunur.
"""

import argparse
import csv
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.primaryType",
    "places.primaryTypeDisplayName",
    "places.pureServiceAreaBusiness",
    "nextPageToken",
])
# İlçənin sərhədini öyrənmək üçün (yalnız sorğu limitə çatanda, ucuz Pro tarifi)
VIEWPORT_FIELD_MASK = "places.id,places.types,places.viewport"
PAGE_SIZE = 20
MAX_PAGES = 3  # Google bir sorğu üçün ən çox 60 nəticə qaytarır
MAX_SPLIT_DEPTH = 2  # limitə çatan sorğu ərazisi neçə dəfə 4 hissəyə bölünə bilər
MAX_RETRIES = 4
RETRY_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_MAX_CALLS = 900  # Enterprise tarifinin aylıq 1000 pulsuz çağırışından aşağı

# İzmir vilayətinin təxmini sərhədləri (bölünən ərazilər bundan kənara çıxmır)
IZMIR_BOUNDS = {"low": (37.70, 26.10), "high": (39.50, 28.55)}

IZMIR_DISTRICTS = [
    "Aliağa", "Balçova", "Bayındır", "Bayraklı", "Bergama", "Beydağ",
    "Bornova", "Buca", "Çeşme", "Çiğli", "Dikili", "Foça",
    "Gaziemir", "Güzelbahçe", "Karabağlar", "Karaburun", "Karşıyaka", "Kemalpaşa",
    "Kınık", "Kiraz", "Konak", "Menderes", "Menemen", "Narlıdere",
    "Ödemiş", "Seferihisar", "Selçuk", "Tire", "Torbalı", "Urla",
]

# "protez laboratuvarı" yoxdur: o, ortopedik (protez-ortez) labları da gətirir
KEYWORDS = [
    "diş protez laboratuvarı",
    "dental laboratuvar",
    "diş laboratuvarı",
    "diş teknisyeni",
]

# Adına görə "lab" sayılan yerlər; qalanları "Yoxlanmalı" vərəqinə düşür.
# Bütün regex-lər normalize() olunmuş (ASCII, kiçik hərf) ada tətbiq olunur.
LAB_RE = re.compile(r"\blab|labs?\b|laboratuv|protez|teknisyen|zirkon|porselen|cad ?/?cam")
STRONG_LAB_RE = re.compile(r"\blab|labs?\b|laboratuv|teknisyen|cad ?/?cam")
DENTAL_RE = re.compile(r"\bdis\b|dental|zirkon|porselen|ortodon|implant")
CLINIC_RE = re.compile(
    r"klini|clinic|dentist|hekim|agiz (ve )?dis|\badsm\b|\bcent(er|re)\b|dis merkezi|saglik merkezi|"
    r"\bdt\b|\bdr\b|muayenehane"
)
NON_DENTAL_RE = re.compile(
    r"tahlil|tibbi|\btip\b|biyokimya|patoloji|mikrobiyoloji|goruntuleme|rontgen|"
    r"veteriner|gida|analiz|kalibrasyon|cevre|hormon|genetik|"
    r"ortez|ortopedi|orto ?protez|goz protez|bacak|\bkol\b|optik|isitme|\bsac(lar|i)?\b|hair|medikal"
)

COLUMNS = [
    ("name", "Ad"),
    ("district", "İlçə"),
    ("address", "Ünvan"),
    ("phone", "Telefon"),
    ("website", "Sayt"),
    ("rating", "Reytinq"),
    ("reviews", "Rəy sayı"),
    ("maps_url", "Maps linki"),
    ("category", "Google kateqoriyası"),
    ("note", "Qeyd"),
    ("lat", "Lat"),
    ("lng", "Lng"),
    ("keywords", "Tapıldığı açar sözlər"),
]
LINK_FIELDS = {"website", "maps_url"}

_TR_MAP = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû", "iiissgguuooccaaiiuu")


class PlacesError(RuntimeError):
    pass


class CallLimitReached(PlacesError):
    pass


def log(message):
    print(message, file=sys.stderr, flush=True)


def normalize(text):
    """Türk hərflərini ASCII-yə çevirib kiçik hərfə salır: 'Karşıyaka' -> 'karsiyaka'."""
    text = (text or "").translate(_TR_MAP).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


class PlacesClient:
    def __init__(self, api_key, session=None, sleep=time.sleep, max_calls=None):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.sleep = sleep
        self.max_calls = max_calls
        self.request_count = 0
        self._viewports = {}

    def _post(self, body, field_mask=FIELD_MASK):
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        error = ""
        for attempt in range(MAX_RETRIES + 1):
            if self.max_calls is not None and self.request_count >= self.max_calls:
                raise CallLimitReached(
                    f"API çağırış limiti ({self.max_calls}) doldu. Daha çox lazımdırsa, "
                    "--max-calls ilə artırın (aylıq pulsuz limiti nəzərə alın)."
                )
            self.request_count += 1
            try:
                resp = self.session.post(SEARCH_URL, json=body, headers=headers, timeout=30)
            except requests.RequestException as exc:
                error = str(exc)
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError:
                        raise PlacesError("Google Places API-dən oxunmayan cavab gəldi") from None
                error = _error_message(resp)
                if resp.status_code not in RETRY_STATUSES:
                    raise PlacesError(f"Google Places API səhvi ({resp.status_code}): {error}")
            if attempt < MAX_RETRIES:
                self.sleep(2 ** (attempt + 1))
        raise PlacesError(f"Google Places API cavab vermədi: {error}")

    def search_text(self, text_query, rect=None, sink=None):
        """Bir mətn sorğusunun bütün səhifələrini (ən çox 60 nəticə) qaytarır.

        Hər səhifə gələn kimi `sink`-ə də əlavə olunur ki, sorğu yarıda kəsilsə, ödənilmiş nəticə itməsin.
        """
        body = {
            "textQuery": text_query,
            "languageCode": "tr",
            "regionCode": "TR",
            "pageSize": PAGE_SIZE,
            "includePureServiceAreaBusinesses": True,
        }
        if rect:
            body["locationRestriction"] = {"rectangle": rect}
        places = []
        for _ in range(MAX_PAGES):
            data = self._post(body)
            page = data.get("places", [])
            places.extend(page)
            if sink is not None:
                sink.extend(page)
            token = data.get("nextPageToken")
            if not token:
                break
            body = {**body, "pageToken": token}
        return places

    def district_viewport(self, district):
        """İlçənin Google-dakı sərhəd düzbucaqlısı (tapılmasa None). Hər ilçə üçün bir dəfə soruşulur."""
        if district not in self._viewports:
            body = {"textQuery": f"{district}, İzmir", "languageCode": "tr", "regionCode": "TR", "pageSize": 5}
            places = [p for p in self._post(body, VIEWPORT_FIELD_MASK).get("places", []) if p.get("viewport")]
            areas = [p for p in places if "administrative_area_level_2" in p.get("types", [])]
            self._viewports[district] = areas[0]["viewport"] if areas else None
        return self._viewports[district]


def _error_message(resp):
    try:
        return resp.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return resp.text[:300]


def _rect(low_lat, low_lng, high_lat, high_lng):
    return {
        "low": {"latitude": low_lat, "longitude": low_lng},
        "high": {"latitude": high_lat, "longitude": high_lng},
    }


def bounding_box(places, margin=0.25, min_pad=0.01):
    """Nəticələri əhatə edən, hər tərəfdən genişləndirilmiş düzbucaqlı."""
    coords = [
        (p["location"]["latitude"], p["location"]["longitude"])
        for p in places
        if "latitude" in p.get("location", {}) and "longitude" in p.get("location", {})
    ]
    if not coords:
        return None
    lats, lngs = zip(*coords)
    pad_lat = max((max(lats) - min(lats)) * margin, min_pad)
    pad_lng = max((max(lngs) - min(lngs)) * margin, min_pad)
    return _rect(min(lats) - pad_lat, min(lngs) - pad_lng, max(lats) + pad_lat, max(lngs) + pad_lng)


def union_rect(*rects):
    rects = [r for r in rects if r]
    if not rects:
        return None
    return _rect(
        min(r["low"]["latitude"] for r in rects),
        min(r["low"]["longitude"] for r in rects),
        max(r["high"]["latitude"] for r in rects),
        max(r["high"]["longitude"] for r in rects),
    )


def clamp_to_izmir(rect):
    """Düzbucaqlını İzmir sərhədinə kəsir; kəsişmə yoxdursa None."""
    if not rect:
        return None
    (bound_low_lat, bound_low_lng), (bound_high_lat, bound_high_lng) = IZMIR_BOUNDS["low"], IZMIR_BOUNDS["high"]
    low_lat = max(rect["low"]["latitude"], bound_low_lat)
    low_lng = max(rect["low"]["longitude"], bound_low_lng)
    high_lat = min(rect["high"]["latitude"], bound_high_lat)
    high_lng = min(rect["high"]["longitude"], bound_high_lng)
    if low_lat >= high_lat or low_lng >= high_lng:
        return None
    return _rect(low_lat, low_lng, high_lat, high_lng)


def split_rect(rect):
    low_lat, low_lng = rect["low"]["latitude"], rect["low"]["longitude"]
    high_lat, high_lng = rect["high"]["latitude"], rect["high"]["longitude"]
    mid_lat, mid_lng = (low_lat + high_lat) / 2, (low_lng + high_lng) / 2
    return [
        _rect(low_lat, low_lng, mid_lat, mid_lng),
        _rect(low_lat, mid_lng, mid_lat, high_lng),
        _rect(mid_lat, low_lng, high_lat, mid_lng),
        _rect(mid_lat, mid_lng, high_lat, high_lng),
    ]


def search_area(client, text_query, district=None, rect=None, depth=0, sink=None):
    """Sorğu 60 nəticə limitinə çatırsa, ərazini 4 hissəyə bölüb hər birində yenidən axtarır.

    İlk bölünmədə ərazi ilçənin Google-dakı sərhədi ilə nəticələrin əhatəsinin birləşməsidir,
    belə ki, ilçənin kənar hissələri də axtarılır. Bütün nəticələr `sink`-ə yığılır və qaytarılır;
    axtarış yarıda kəsilsə, o ana qədər gələnlər `sink`-də qalır.
    """
    sink = [] if sink is None else sink
    places = client.search_text(text_query, rect, sink=sink)
    if len(places) < PAGE_SIZE * MAX_PAGES:
        return sink
    if depth >= MAX_SPLIT_DEPTH:
        log(f"  xəbərdarlıq: '{text_query}' bölündükdən sonra da limitə çatır, bəzi nəticələr itə bilər")
        return sink
    area = rect
    if area is None:
        viewport = client.district_viewport(district) if district else None
        area = clamp_to_izmir(union_rect(viewport, bounding_box([p for p in places if is_in_izmir(p)])))
        if area is None:
            log(f"  xəbərdarlıq: '{text_query}' limitə çatdı, amma ərazi təyin olunmadı; bəzi nəticələr itə bilər")
            return sink
    for quadrant in split_rect(area):
        search_area(client, text_query, district, quadrant, depth + 1, sink)
    return sink


def address_component(place, component_type):
    for comp in place.get("addressComponents", []):
        if component_type in comp.get("types", []):
            return comp.get("longText", "")
    return ""


def is_in_izmir(place):
    province = address_component(place, "administrative_area_level_1")
    if province:
        return normalize(province) == "izmir"
    return "izmir" in normalize(place.get("formattedAddress", ""))


def is_hidden_address(place):
    """Ünvanını gizlədən (yalnız xidmət ərazisi göstərən) biznes."""
    return bool(place.get("pureServiceAreaBusiness")) and not place.get("formattedAddress")


def district_of(place, fallback):
    district = address_component(place, "administrative_area_level_2")
    if district:
        return district
    match = re.search(r"([^\s,/]+)/[İI]zmir", place.get("formattedAddress", ""))
    return match.group(1) if match else fallback


def is_likely_lab(name):
    n = normalize(name)
    if not LAB_RE.search(n):
        return False
    if NON_DENTAL_RE.search(n) and not DENTAL_RE.search(n):
        return False  # tibbi/ortopedik/eşitmə və s. laboratoriyalar
    if CLINIC_RE.search(n) and not STRONG_LAB_RE.search(n):
        return False  # "Zirkonyum Diş Kliniği" kimi klinikalar
    return True


def build_queries(districts, keywords):
    return [(d, k, f"{k} {d} İzmir") for d in districts for k in keywords]


def collect(client, queries, records):
    """Bütün sorğuları işlədir, nəticələri place id üzrə `records`-a yığır (təkrarlar birləşir)."""
    for i, (district, keyword, text_query) in enumerate(queries, 1):
        places = []
        try:
            search_area(client, text_query, district, sink=places)
        finally:
            # Sorğu yarıda kəsilsə də (limit, səhv, Ctrl+C), artıq gələn nəticələr saxlanır
            new = 0
            for place in places:
                place_id = place.get("id")
                if not place_id:
                    continue
                rec = records.get(place_id)
                if rec is None:
                    rec = records[place_id] = {"place": place, "keywords": {}, "query_district": district}
                    new += 1
                rec["keywords"][keyword] = None  # dict: sıra qorunur, təkrar olmur
            log(f"[{i}/{len(queries)}] {text_query}: {len(places)} nəticə, {new} yeni")
    return records


def build_rows(records):
    labs, review = [], []
    skipped = {"closed": 0, "outside": 0}
    for rec in records.values():
        place = rec["place"]
        status = place.get("businessStatus")
        hidden = is_hidden_address(place)
        if status == "CLOSED_PERMANENTLY":
            skipped["closed"] += 1
            continue
        if not hidden and not is_in_izmir(place):
            skipped["outside"] += 1
            continue
        notes = []
        if status == "CLOSED_TEMPORARILY":
            notes.append("Müvəqqəti bağlı")
        if hidden:
            notes.append("Ünvan gizlədilib (xidmət ərazisi)")
        location = place.get("location", {})
        row = {
            "name": place.get("displayName", {}).get("text", ""),
            "district": district_of(place, rec["query_district"]),
            "address": place.get("formattedAddress", ""),
            "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber", ""),
            "website": place.get("websiteUri", ""),
            "rating": place.get("rating", ""),
            "reviews": place.get("userRatingCount", ""),
            "maps_url": place.get("googleMapsUri", ""),
            "category": place.get("primaryTypeDisplayName", {}).get("text") or place.get("primaryType", ""),
            "note": "; ".join(notes),
            "lat": location.get("latitude", ""),
            "lng": location.get("longitude", ""),
            "keywords": ", ".join(rec["keywords"]),
        }
        # Ünvanı gizli olanın İzmirdə olduğu yoxlana bilmir, ona görə həmişə "Yoxlanmalı"
        (labs if is_likely_lab(row["name"]) and not hidden else review).append(row)
    sort_key = lambda r: (normalize(r["district"]), normalize(r["name"]))  # noqa: E731
    labs.sort(key=sort_key)
    review.sort(key=sort_key)
    return labs, review, skipped


def write_csv(path, labs, review):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Növ"] + [title for _, title in COLUMNS])
        for kind, rows in (("Lab", labs), ("Yoxlanmalı", review)):
            for row in rows:
                writer.writerow([kind] + [row[key] for key, _ in COLUMNS])


def _xlsx_value(value):
    return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value


def write_xlsx(path, labs, review):
    wb = Workbook()
    for index, (title, rows) in enumerate((("Lablar", labs), ("Yoxlanmalı", review))):
        ws = wb.active if index == 0 else wb.create_sheet()
        ws.title = title
        ws.append([t for _, t in COLUMNS])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([_xlsx_value(row[key]) for key, _ in COLUMNS])
        for col, (key, _) in enumerate(COLUMNS, 1):
            if key in LINK_FIELDS:
                for r in range(2, ws.max_row + 1):
                    cell = ws.cell(row=r, column=col)
                    if cell.value:
                        cell.hyperlink = cell.value
                        cell.style = "Hyperlink"
        widths = {"name": 40, "district": 14, "address": 60, "phone": 18, "website": 35,
                  "maps_url": 35, "category": 22, "note": 18, "keywords": 40}
        for col, (key, _) in enumerate(COLUMNS, 1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = widths.get(key, 12)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.save(path)


def output_paths(base):
    """'output/izmir' -> output/izmir.csv, output/izmir.xlsx (adda nöqtə olsa da kəsilmir)."""
    if base.suffix.lower() in (".csv", ".xlsx"):
        base = base.with_suffix("")
    return base.with_name(base.name + ".csv"), base.with_name(base.name + ".xlsx")


def check_writable(paths):
    """API-yə pul xərcləmədən əvvəl fayllara yazmaq mümkün olduğunu yoxlayır. Problem varsa mətnini qaytarır."""
    for path in paths:
        existed = path.exists()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            open(path, "a").close()
        except OSError as exc:
            return f"{path} faylına yazmaq olmur ({exc}). Fayl Excel-də açıqdırsa, bağlayın."
        if not existed:
            path.unlink()
    return None


def save_outputs(base, labs, review):
    """CSV və Excel yazır. Fayl tutulubsa, tarixli adla yazır ki, nəticə itməsin."""
    saved = []
    for path, writer in zip(output_paths(base), (write_csv, write_xlsx)):
        try:
            writer(path, labs, review)
        except OSError as exc:
            fallback = path.with_name(path.stem + time.strftime("_%Y%m%d_%H%M%S") + path.suffix)
            log(f"{path} yazıla bilmədi ({exc}), əvəzinə {fallback} yazılır")
            try:
                writer(fallback, labs, review)
            except OSError as exc2:
                log(f"{fallback} də yazıla bilmədi: {exc2}")
                continue
            path = fallback
        saved.append(path)
    return saved


def resolve_districts(names):
    if not names:
        return list(IZMIR_DISTRICTS)
    by_norm = {normalize(d): d for d in IZMIR_DISTRICTS}
    unknown = [n for n in names if normalize(n) not in by_norm]
    if unknown:
        raise SystemExit(
            f"Naməlum ilçə: {', '.join(unknown)}\nMövcud ilçələr: {', '.join(IZMIR_DISTRICTS)}"
        )
    return list(dict.fromkeys(by_norm[normalize(n)] for n in names))


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="İzmir diş protez laboratoriyalarını Google Places API ilə tapır."
    )
    parser.add_argument("--districts", nargs="+", metavar="İLÇƏ",
                        help="yalnız bu ilçələr (default: İzmirin bütün 30 ilçəsi)")
    parser.add_argument("--keywords", nargs="+", metavar="SÖZ",
                        help="açar sözlər (default: " + "; ".join(KEYWORDS) + ")")
    parser.add_argument("--output", default="output/izmir_dis_protez_lab",
                        help="çıxış faylının adı, uzantısız (default: %(default)s)")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, metavar="N",
                        help="ən çox bu qədər API çağırışı et, sonra dayanıb tapılanları yaz "
                             "(default: %(default)s; 0 = limitsiz)")
    parser.add_argument("--dry-run", action="store_true",
                        help="API-yə getmədən sorğuları və təxmini çağırış sayını göstər")
    args = parser.parse_args(argv)
    if args.max_calls < 0:
        parser.error("--max-calls mənfi ola bilməz")
    if Path(args.output).name in ("", ".", ".."):
        parser.error("--output fayl adı olmalıdır, məs. output/izmir")
    return args


def main(argv=None):
    args = parse_args(argv)
    districts = resolve_districts(args.districts)
    keywords = list(dict.fromkeys(args.keywords or KEYWORDS))
    queries = build_queries(districts, keywords)

    if args.dry_run:
        for _, _, text_query in queries:
            print(text_query)
        n = len(queries)
        worst = n * MAX_PAGES * sum(4 ** d for d in range(MAX_SPLIT_DEPTH + 1)) + len(districts)
        print(f"\n{n} sorğu. Adətən {n}–{n * MAX_PAGES} API çağırışı; sıx ilçələrdə ərazi bölündükcə "
              f"artır (ən pis halda ~{worst}).")
        print(f"--max-calls limiti: {args.max_calls or 'limitsiz'}")
        return 0

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        log("GOOGLE_MAPS_API_KEY tapılmadı. Açarı environment variable kimi əlavə edin (README-yə baxın).")
        return 1

    base = Path(args.output)
    problem = check_writable(output_paths(base))
    if problem:
        log(problem)
        return 1

    client = PlacesClient(api_key, max_calls=args.max_calls or None)
    records = {}
    exit_code = 0
    try:
        collect(client, queries, records)
    except (PlacesError, KeyboardInterrupt) as exc:
        log(f"\n{str(exc) or 'Dayandırıldı (Ctrl+C).'}")
        if not records:
            print(f"API çağırışı: {client.request_count}. Heç nə tapılmadı, fayl yazılmadı.")
            return 1
        log("Axtarış yarımçıq qaldı, indiyə qədər tapılanlar yazılır.")
        exit_code = 1

    labs, review, skipped = build_rows(records)
    saved = save_outputs(base, labs, review)
    if not saved:
        exit_code = 1

    counts = {}
    for kind, rows in (("lab", labs), ("review", review)):
        for row in rows:
            counts.setdefault(row["district"], {"lab": 0, "review": 0})[kind] += 1
    print("\nİlçə üzrə nəticə (lab / yoxlanmalı):")
    for district in sorted(counts, key=normalize):
        print(f"  {district:<14} {counts[district]['lab']:>4} / {counts[district]['review']}")
    print(f"\nCəmi: {len(labs)} lab, {len(review)} yoxlanmalı. "
          f"Atılan: {skipped['closed']} bağlı, {skipped['outside']} İzmirdən kənar.")
    print(f"API çağırışı: {client.request_count}")
    print(f"Fayllar: {', '.join(str(p) for p in saved) or 'yazıla bilmədi'}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
