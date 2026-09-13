# Neyron Laboratoriyası

An interactive, phone-first playground for learning how a neural network
actually works — built from scratch, no machine-learning library.

Open `index.html` in any browser. There is no build step, no server, and no
dependency beyond a web font.

## What's inside

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

Bu səhifə neyron şəbəkənin necə işlədiyini **oxuyaraq deyil, oynadaraq**
öyrətmək üçün qurulub. Telefonda açılır, heç nə quraşdırmaq lazım deyil.

**Üç addım, üç sual:**

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
