# New-idea

## İzmir diş protez laboratoriyaları: `lab_finder.py`

Google Maps-dəki məlumatı rəsmi **Google Places API (New)** ilə çəkir. İzmirin 30 ilçəsinin hər birində bir neçə açar sözlə axtarır, təkrarları silir və nəticəni Excel/CSV faylına yazır.

Web axtarışı yalnız saytı olan yerləri tapır. Bu skript isə Maps-in öz bazasından oxuyur, ona görə saytı olmayan labları da görür.

### Birdəfəlik qurulma

1. [Google Cloud Console](https://console.cloud.google.com/)-da yeni layihə yaradın.
2. **Billing** bölməsində layihəyə kart qoşun. Billing olmadan API işləmir.
3. **APIs & Services → Library** bölməsində **Places API (New)**-i aktiv edin.
4. **APIs & Services → Credentials → Create credentials → API key** ilə açar yaradın. Sonra açarı yalnız **Places API (New)** ilə məhdudlaşdırın (*API restrictions*).
5. Pulu qorumaq üçün (tövsiyə olunur):
   - **APIs & Services → Places API (New) → Quotas** bölməsində Text Search üçün gündəlik sorğu limiti qoyun (məs. 1000). Bu, limitdən sonra sorğuları həqiqətən dayandırır.
   - **Billing → Budgets & alerts** bölməsində büdcə xəbərdarlığı qurun (məs. $5). Bu yalnız e-poçt göndərir, xərci dayandırmır.
6. Açarı `GOOGLE_MAPS_API_KEY` adlı environment variable kimi verin. Açarı heç vaxt chat-ə yazmayın.
   - **Claude Code cloud session:** session başlığındakı environment menyusu → **Edit** → environment variables bölməsinə `GOOGLE_MAPS_API_KEY=...` əlavə edin. Yeni session onu görəcək.
   - **Windows (PowerShell):** `$env:GOOGLE_MAPS_API_KEY="..."` (yalnız həmin pəncərə üçün). Daimi etmək üçün: `setx GOOGLE_MAPS_API_KEY "..."`, sonra yeni pəncərə açın.
   - **macOS / Linux:** `export GOOGLE_MAPS_API_KEY=...`

### İstifadə

```bash
pip install -r requirements.txt

python lab_finder.py --dry-run                          # API-yə getmədən sorğuları və təxmini çağırış sayını göstərir
python lab_finder.py --districts Karşıyaka              # əvvəlcə bir ilçə ilə yoxlayın
python lab_finder.py --districts Karşıyaka Bornova Çiğli
python lab_finder.py                                    # bütün İzmir
```

macOS/Linux-da `python` əvəzinə `python3`, Windows-da `py` yazmaq lazım ola bilər (`py -m pip install -r requirements.txt`).

İlçə adlarını Türk hərfləri olmadan da yazmaq olar (`karsiyaka`, `cigli`).

Əlavə seçimlər:
- `--max-calls N`: ən çox N API çağırışı et (default **900**, `0` = limitsiz). Limit dolanda skript dayanır və indiyə qədər tapılanları yazır.
- `--keywords "dental lab" "zirkonyum laboratuvarı"`: öz açar sözləriniz
- `--output output/karsiyaka`: çıxış faylının adı (uzantısız). Hər işə salmada eyni ad üzərinə yazılır, köhnə nəticəni saxlamaq istəyirsinizsə başqa ad verin.

Yenidən işə salmadan əvvəl köhnə Excel faylını bağlayın. Fayl açıq qalarsa, skript API-yə getmədən xəbərdarlıq edir. İş zamanı açılsa, nəticə tarixli adla (məs. `izmir_dis_protez_lab_20261005_143000.xlsx`) yazılır.

Ctrl+C ilə dayandırsanız, o ana qədər tapılanlar yenə fayla yazılır.

### Nəticə

`output/` qovluğunda iki fayl yaranır:

- **`izmir_dis_protez_lab.xlsx`**, iki vərəqlə:
  - **Lablar**: adına görə diş protez laboratoriyası olanlar. Adında *lab, laboratuvar, protez, teknisyen, zirkon, porselen, CAD/CAM* kimi sözlər olur. Klinikalar (*klinik, hekim, Dt., Dr.*), ortopedik protez-ortez, tibbi tahlil, optik, eşitmə cihazı kimi yerlər buraya düşmür.
  - **Yoxlanmalı**: axtarışda çıxan, amma adından diş protez labı olduğu bilinməyənlər (məs. diş klinikaları) və ünvanını gizlədən (yalnız xidmət ərazisi göstərən) bizneslər. Bunlar silinmir, gözdən keçirmək üçün ayrıca saxlanır.
- **`izmir_dis_protez_lab.csv`**: eyni məlumat, `Növ` sütunu ilə (`Lab` / `Yoxlanmalı`). Türk dilli Excel CSV-ni tək sütunda aça bilər, ona görə Excel üçün `.xlsx` faylını açın.

Sütunlar: Ad, İlçə, Ünvan, Telefon, Sayt, Reytinq, Rəy sayı, Maps linki, Google kateqoriyası, Qeyd (müvəqqəti bağlı / ünvan gizli), Lat, Lng, Tapıldığı açar sözlər.

Daimi bağlanmış yerlər və İzmirdən kənarda olanlar atılır. Onların sayı sonda ekranda göstərilir.

### Necə işləyir

- Hər `açar söz × ilçə` cütü üçün `"<açar söz> <ilçə> İzmir"` sorğusu göndərilir. Default açar sözlər: *diş protez laboratuvarı, dental laboratuvar, diş laboratuvarı, diş teknisyeni*.
- Google bir sorğu üçün ən çox 60 nəticə (3 səhifə × 20) qaytarır. Sorğu bu limitə çatırsa, ilçənin Google-dakı sərhədi götürülür, 4 hissəyə bölünür və hər hissədə yenidən axtarılır (ən çox 2 səviyyə, yəni 16 hissəyə qədər).
- Eyni yer bir neçə sorğuda çıxırsa, Google `place id`-si ilə bir sətirə birləşdirilir.

### Xərc

- Telefon, sayt və reytinq sahələri istədiyi üçün hər çağırış Text Search-in **Enterprise** tarifinə düşür. Google bu tarifdə ayda **1000 çağırışı pulsuz** verir, sonra təxminən **hər 1000 çağırış üçün $35** alır. Rəqəmlər dəyişə bilər, [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing) səhifəsindən yoxlayın.
- Bütün İzmir standart ayarlarla 120 sorğudur. Sakit ilçələrdə hər sorğu 1–3 çağırışdır, yəni təxminən 120–360. Amma sıx ilçələrdə (Konak, Bornova, Karşıyaka, Buca...) 60 limitinə çatan hər sorğu bölünmə ilə **63 çağırışa qədər** gedə bilər. Bu halda tam axtarış 1000-i keçə bilər.
- `--dry-run` sorğuların dəqiq siyahısını, çağırış sayının isə yalnız təxmini aralığını və ən pis halını göstərir.
- Default `--max-calls 900` limiti bir işə salmanı pulsuz həddin altında saxlayır. Amma aylıq limit bütün işə salmaların cəmidir. Hər işə salmanın sonunda `API çağırışı: N` sətrinə baxın.
- Tövsiyə: əvvəlcə bir ilçə ilə yoxlayın, sonra lazım olsa `--max-calls`-u artırın.

### Testlər

```bash
python -m unittest discover -s tests
```

Testlər API açarı tələb etmir, Google cavabları saxta (mock) obyektlərlə yoxlanır.
