# Neyron Laboratoriyası

Two interactive, phone-first pages for learning how a neural network actually
works — built from scratch, no machine-learning library.

| File | What it is | Start here? |
|---|---|---|
| `ders.html` | **Neyron Dərsi** — a 12-card guided lesson that asks you to predict before it reveals | **yes** |
| `index.html` | **Neyron Laboratoriyası** — the free-play sandbox, all three stages on one scrolling page | after the lesson |

Open either in any browser. There is no build step, no server, and no dependency
beyond a web font.

## The lesson (`ders.html`)

One idea per card, never a long scroll. Cards that teach a rule follow the same
three beats: **probe** (something to move) → **prediction** (a question you
answer before seeing the result) → **reveal**.

It opens on a decision anyone already knows how to make — *should I wear a
jacket?* — with two plain "how much does this matter to me" sliders, and only
names them `çəki`/weight once you have already used them. Bias, sigmoid, loss,
one manual gradient step, then the hidden layer follow from there. The single
most important card is `Bir addım`: one gradient step per click, with the
weights and loss before and after side by side.

## The sandbox (`index.html`)

A single self-contained page with three stages, each answering one question:

1. **Neyron nədir?** — one neuron with draggable weights. The formula renders
   with the live numbers substituted, so multiply-add-squash stops being
   abstract.
2. **Öyrənmə nədir?** — the same neuron trains itself on tappable data. The
   weights from stage 1 now move on their own while the loss curve falls.
3. **Niyə "dərin"?** — a hidden layer. On the circle dataset, 0 hidden neurons
   stalls at ~54% accuracy and 8 reaches 100%. Per-neuron thumbnails show that
   every hidden neuron still draws a *straight* line; only their sum curves.

## The network

Implemented by hand in `index.html`, roughly 120 lines:

- Architecture `2 → [h] → 1`, `tanh` hidden activation, `sigmoid` output
- Binary cross-entropy loss
- Full-batch gradient descent with momentum
- Explicit forward and backward passes — comments name each term (`dL/dz`,
  `dL/dW`) so the code reads as the reference implementation

The decision surface is evaluated on a 64×64 grid and scaled up, which keeps it
at 60fps on a phone. A seeded PRNG makes every reset reproducible.

Measured accuracy after 6000 steps (seed 11):

| dataset | 0 hidden | 4 hidden | 8 hidden |
|---|---|---|---|
| circle | 54.2% | 100% | 100% |
| spiral | 61.7% | — | 100% |
| xor    | — | — | 100% |

---

## Azərbaycanca — nə üçün lazımdır

Bu səhifələr neyron şəbəkənin necə işlədiyini **oxuyaraq deyil, oynadaraq**
öyrətmək üçün qurulub. Telefonda açılır, heç nə quraşdırmaq lazım deyil.

**Hansından başlamalı:**

1. Əvvəlcə **`ders.html`** — addım-addım gedən dərs. 12 kart, hər kartda bir
   fikir. Səndən əvvəlcə proqnoz soruşur, sonra cavabı göstərir. Texniki sözlə
   yox, tanış bir sualla başlayır: “gödəkçə geyinim?”
2. Sonra **`index.html`** — sərbəst laboratoriya. Burada XOR, spiral kimi daha
   çətin formalar və öz nöqtələrini əlavə etmək imkanı var.

**Laboratoriyadakı üç addım:**

1. **Neyron nədir?** Sürgüləri çəkirsən, çıxışın necə dəyişdiyini görürsən.
   Nəticə: neyron sadəcə *vur → topla → sıxışdır* əməliyyatıdır. Və çəkdiyi
   sərhəd həmişə **düz xətdir**.
2. **Öyrənmə nədir?** İndi çəkiləri kompüter özü tapır. Eyni `w₁ w₂ b`
   rəqəmlərinin öz-özünə dəyişdiyini, itki əyrisinin aşağı düşdüyünü izləyirsən.
   "Öyrənmə" məhz budur — başqa sehr yoxdur.
3. **Niyə "dərin"?** Dairə formasında 0 gizli neyron bacarmır (~54%), 8 neyron
   isə 100%-ə çatır. Kiçik pəncərələr göstərir ki, hər gizli neyron **hələ də
   düz xətt** çəkir — əyri sərhəd onların cəmindən yaranır. Dərin öyrənmənin
   bütün ideyası budur.

**Terminlər:**

| Azərbaycanca | İngiliscə | Nə deməkdir |
|---|---|---|
| çəki | weight | girişin nə qədər vacib olduğu |
| sürüşmə | bias | qərarın nə qədər asan verildiyi |
| itki | loss | təxminin düzgün cavabdan uzaqlığı |
| qradiyent | gradient | hansı çəkinin səhvə nə qədər günahkar olduğu |
| geri yayılma | backpropagation | günahı çıxışdan girişə doğru paylamaq |

**Növbəti addımlar:** eyni şəbəkəni Python + NumPy ilə yazmaq, sonra PyTorch ilə
müqayisə etmək, sonra Azərbaycan mətni üzrə kiçik dil modeli (mini-GPT)
öyrətmək.
