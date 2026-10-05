# New-idea

## İzmir diş protez laboratoriyaları: `lab_finder.py`

Google Maps-dəki məlumatı rəsmi **Google Places API (New)** ilə çəkir. İzmirin 30 ilçəsinin hər birində bir neçə açar sözlə axtarır, təkrarları silir və nəticəni Excel/CSV faylına yazır.

Web axtarışı yalnız saytı olan yerləri tapır. Bu skript isə Maps-in öz bazasından oxuyur, ona görə saytı olmayan labları da görür.

### Birdəfəlik qurulma

1. [Google Cloud Console](https://console.cloud.google.com/)-da yeni layihə yaradın.
2. **APIs & Services → Library** bölməsində **Places API (New)**-i aktiv edin.
3. **Billing** bölməsində layihəyə kart qoşun. Kiçik həcm aylıq pulsuz limitin içində qalır, amma billing olmadan API işləmir.
4. **APIs & Services → Credentials → Create credentials → API key** ilə açar yaradın. Sonra açarı yalnız **Places API (New)** ilə məhdudlaşdırın (*API restrictions*).
5. Tövsiyə: **Billing → Budgets & alerts** bölməsində kiçik büdcə xəbərdarlığı qurun (məs. $5).
6. Açarı `GOOGLE_MAPS_API_KEY` adlı environment variable kimi verin:
   - **Claude Code cloud session:** session başlığındakı environment menyusu → **Edit** → environment variables bölməsinə `GOOGLE_MAPS_API_KEY=...` əlavə edin. Yeni session onu görəcək. Açarı chat-ə yazmayın.
   - **Öz kompüterinizdə:** `export GOOGLE_MAPS_API_KEY=...`

### İstifadə

```bash
pip install -r requirements.txt

python lab_finder.py --dry-run                          # API-yə getmədən sorğuları və təxmini sayını göstərir
python lab_finder.py --districts Karşıyaka              # əvvəlcə bir ilçə ilə yoxlayın
python lab_finder.py --districts Karşıyaka Bornova Çiğli
python lab_finder.py                                    # bütün İzmir
```

İlçə adlarını Türk hərfləri olmadan da yazmaq olar (`karsiyaka`, `cigli`).

Əlavə seçimlər:
- `--keywords "dental lab" "zirkonyum laboratuvarı"`: öz açar sözləriniz
- `--output output/karsiyaka`: çıxış faylının adı (uzantısız)

### Nəticə

`output/` qovluğunda iki fayl yaranır:

- **`izmir_dis_protez_lab.xlsx`**, iki vərəqlə:
  - **Lablar**: adına görə diş protez laboratoriyası olanlar (adında *lab, protez, teknisyen, zirkon, seramik, porselen, CAD/CAM* sözləri var)
  - **Yoxlanmalı**: axtarışda çıxan, amma adından lab olduğu bilinməyənlər (məs. diş klinikaları). Bunlar silinmir, gözdən keçirmək üçün ayrıca saxlanır.
- **`izmir_dis_protez_lab.csv`**: eyni məlumat, `Növ` sütunu ilə (`Lab` / `Yoxlanmalı`)

Sütunlar: Ad, İlçə, Ünvan, Telefon, Sayt, Reytinq, Rəy sayı, Maps linki, Google kateqoriyası, Qeyd (müvəqqəti bağlı olanlar), Lat, Lng, Tapıldığı açar sözlər.

Daimi bağlanmış yerlər və İzmirdən kənarda olanlar atılır. Onların sayı sonda ekranda göstərilir.

### Necə işləyir

- Hər `açar söz × ilçə` cütü üçün `"<açar söz> <ilçə> İzmir"` sorğusu göndərilir.
- Google bir sorğu üçün ən çox 60 nəticə (3 səhifə × 20) qaytarır. Sorğu bu limitə çatırsa, ərazi 4 hissəyə bölünür və hər hissədə yenidən axtarılır (ən çox 2 səviyyə).
- Eyni yer bir neçə sorğuda çıxırsa, Google `place id`-si ilə bir sətirə birləşdirilir.

### Xərc

Bütün İzmir üçün standart ayarlarla 150 sorğu gedir, yəni təxminən 150–450 API çağırışı (`--dry-run` dəqiq sayı göstərir). Telefon və sayt sahələri Text Search-in **Enterprise** tarifinə düşür. Bu tarifin də aylıq pulsuz limiti var, amma dəqiq rəqəmlər üçün [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing) səhifəsinə baxın.

### Testlər

```bash
python -m unittest discover -s tests
```

Testlər API açarı tələb etmir, Google cavabları saxta (mock) obyektlərlə yoxlanır.
