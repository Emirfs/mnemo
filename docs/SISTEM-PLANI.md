# Mnemo Live — Sistem Planı

> AI-native bir terminal ve onun **kalıcı, otomatik hafızası**. Hafıza katmanı
> mevcut **mnemo** vault'u; üstüne yerel (ücretsiz) bir model ile çalışan bir
> **broker** ekliyoruz. Sonuç: terminalde iş yaparken hafıza, kararlar ve
> yapılacaklar manuel `recall` çağırmadan, otomatik olarak kullandığın AI'a akar.

Tarih: 2026-06-23 · Durum: plan (onay bekliyor) · Sahip: Emir Furkan

---

## 1. Yönetici özeti

Bir terminal yazmak işin küçük ve son kısmı. Asıl değer ve asıl iş, **araya
giren hafıza broker'ı**: sen ne yazarsan, arka planda ilgili hafızayı seçip
sıkıştırıp kullandığın AI'a ekleyen sürekli açık bir katman. Bu katman zaten var
olan mnemo vault'unu (markdown + sqlite index + MCP + recall hook) okur.

Kritik tasarım kararı: **hiç LLM yok — ne sıcak yolda, ne arka planda.** Her
prompt'ta yapılan iş saf *retrieval* (sqlite FTS + embedding), ~deci-saniye.
Hafıza kalitesi (tazelik, çelişki çözme, eskime) LLM'siz, **mekanik** kurallarla
sağlanır. Böylece sistem hem hızlı hem hafif, hem de bağımlılıksız.

> **Güncelleme (2026-06-25):** Ollama/yerel-LLM "Librarian" planı **düştü.**
> supermemory karşılaştırması (bkz. §14) sonrası, bizde eksik olan retrieval
> kalitesi parçaları LLM gerektirmeden eklendi: eval harness, recency ağırlığı,
> profile tipi, temporal supersession, ephemeral expire. Hepsi shipped (§10).

Bu plan fazlarda ilerler. Faz 0 bir terminal yazmadan "otomatik hafıza" tezini
kanıtlar; terminal en sona, hazır açık-kaynak bir tabanı çatallayarak gelir.

---

## 2. Vizyon (senin istediğin, damıtılmış)

- Warp/Wave gibi modern, AI-native bir terminal.
- Terminalin **kendi hafızası = mnemo sistemi**.
- O terminalde iş yaparken **`recall` gibi manuel adımlara gerek kalmasın**.
- Terminale bağlı **ücretsiz/yerel bir model** (Ollama), hafızayı ve yapılacak
  işleri özetleyip o an kullandığın AI'a otomatik iletsin.
- Yavaş olmasın, RAM'i şişirmesin.

---

## 3. Temel ilke: ürün hafızadır, ön yüz takılıp çıkarılır

```
       ┌─────────────────────────────────────────────┐
       │  ÖN YÜZLER (değiştirilebilir, ucuz)          │
       │  Claude Code · Cursor · Mnemo Term · TUI     │
       └───────────────┬─────────────────────────────┘
                       │  (MCP / hook / stdin enjeksiyon)
       ┌───────────────▼─────────────────────────────┐
       │  BROKER  (Mnemo Live — sürekli açık, sıcak)  │  ← asıl yeni iş
       │  • retrieval (FTS + embedding)  ← sıcak yol  │
       │  • bağlam paketleyici (token bütçeli)        │
       │  • task/karar yüzeye çıkarıcı                │
       └───────────────┬─────────────────────────────┘
                       │
       ┌───────────────▼─────────────────────────────┐
       │  ÇEKİRDEK  (mnemo — VAR)                     │
       │  vault (markdown)  +  index (sqlite/vec)     │
       │  + kalite (mekanik, LLM'siz):                │
       │    recency · supersession · expire · profile │
       └─────────────────────────────────────────────┘
```

> Eski plandaki **LIBRARIAN (Ollama)** kutusu kaldırıldı. Onun çözeceği iş
> (yeni-eskiyi-geçersiz-kılar, eskime) mekanik kurallarla, LLM olmadan yapılıyor.

Ana fikir: AI'ları yeniden yazmıyoruz. Onlar ön yüz; çekirdek hafızaya
**MCP** ve **hook** ile bağlanırlar. Terminal de sadece bir ön yüz — bu yüzden
en sona bırakılabilir ve hazır bir tabandan türetilir.

---

## 4. Bileşenler

### 4.1 Çekirdek — mnemo (VAR)
- **Vault:** `C:/Users/Emir Furkan/Desktop/mnemo-vault` — Obsidian uyumlu
  markdown. Tipler: `project (MOC) · decision · lesson · reference · daily · note`.
- **Index:** `.mnemo/index.sqlite` (FTS + opsiyonel `sqlite-vec` embedding).
- **Okuma yolları:** MCP server (`memory_search/get/moc/write`) ve SessionStart
  recall hook. İkisi de aynı vault'u okur.
- **Proje tespiti:** git remote slug → klasör adı (örn. `stm32-rf-ota`).

### 4.2 Broker — "Mnemo Live" (YENİ, kalbi bu)
Sürekli açık tek bir process. İçinde embedding modeli **bir kez** yüklenir ve
sıcak kalır (soğuk subprocess başlatma yok). Görevleri:

1. **Retrieval:** gelen prompt/komut + cwd/proje bağlamına göre vault'tan en
   ilgili notları seçer. Saf sqlite FTS + cosine. LLM yok.
2. **Bağlam paketleme:** seçilen notları sert token bütçesine (örn. ≤800 token)
   sıkıştırır; her not zaten "summary-only" tutulduğu için ucuz.
3. **Task/karar yüzeyleme:** açık task'ları ve son kararları "sırada ne var"
   olarak ekler.
4. **Cache:** cwd/proje/task değişmediyse son paketi yeniden kullanır.

Arayüz: yerel bir soket/HTTP endpoint (`localhost`), ör. `GET /context?cwd=...`.
Ön yüzler buradan ister; daemon sıcak olduğu için cevap ~ms.

### 4.3 Enjeksiyon (YENİ)
"Manuel recall'a gerek kalmasın" kısmı. İki mod:
- **Claude Code / MCP'li AI'lar:** `UserPromptSubmit` hook → broker'dan bağlam
  çek → prompt'un başına ekle. Her mesajda taze bağlam (session başında tek sefer
  değil).
- **Terminale gömülü chat (Faz 3):** prompt'u zaten biz kuruyoruz → bağlamı
  doğrudan system prompt'a koyarız.

### 4.4 Kalite katmanı — mekanik, LLM'siz (YENİ, shipped)
Eski "Librarian (Ollama)" planının yerine geçer. supermemory'nin LLM ile yaptığı
fact-yönetimini, biz markdown + sqlite üstünde **kural tabanlı** yapıyoruz —
hiç model yüklemeden, sıcak yola dokunmadan:

- **Recency ağırlığı** (`context.py`): ilgililik skoru tazelikle çarpılır
  (yarı-ömür 120 gün, taban 0.5). Aynı derecede ilgili iki nottan yeni olan öne
  çıkar; eski demote olur. Saf tarih matematiği, ms.
- **Temporal supersession** (`note.py` + `writer.py`): `mnemo write
  --supersedes <id,…>` yeni notu yazar, eskileri `status: superseded` +
  `superseded_by` ile işaretler. Eski not diskte kalır (tarihçe) ama retrieval'dan
  düşer → "yeni eskiyi geçersiz kılar".
- **Ephemeral expire** (`context.py`): `note`/`daily` tipleri raf ömrünü (90 gün)
  aşınca context paketinden çıkar; vault'ta ve `search`'te durur.
- **Profile tipi** (`note.py`): kullanıcı/stack hakkında statik gerçekler. Sorgu
  bağımsız, her context/recall paketinin başına sabitlenir.
- **Eval harness** (`bench.py` + `mnemo bench`): hit-rate / MRR / mean-recall.
  Her kalite değişikliğini ölç-doğrula.

İleride LLM distill istenirse Faz 2 olarak geri eklenebilir; şimdilik kapsam dışı.

### 4.5 Ön yüz / Terminal (EN SON)
Sıfırdan terminal **yazılmaz**. Hazır açık tabanı çatalla:
- **Wave Terminal** (açık kaynak, AI-native) — en yakın hazır temel.
- **Tauri + xterm.js** — tam kontrol, orta efor.
- **Ghostty / TUI** — hafif alternatif.
Broker'a `localhost` üzerinden bağlanır; mnemo eklenti olur.

---

## 5. Veri akışı

**Okuma yolu (sıcak, her prompt) — hedef <100ms:**
```
sen yazarsın
  → enjeksiyon (hook/terminal) broker'a sorar: /context?cwd=…&q=…
  → broker: query embed (sıcak) + sqlite FTS/vektör → top-k not
  → token bütçesine paketle → döndür
  → AI prompt'una eklenir → AI cevaplar
```
LLM çağrısı YOK.

**Yazma yolu (soğuk, nadir, arka plan):**
```
session biter / not değişir
  → librarian iş kuyruğuna eklenir (debounce)
  → Ollama yüklenir → distill/özet/link → draft not yaz → index güncelle
  → Ollama keep_alive sonunda boşalır
```
Sen beklemezsin.

---

## 6. Performans tasarımı

| İş | Süre | Yol |
|---|---|---|
| FTS sorgu | ~1–5ms | sıcak |
| query embed (model RAM'de) | ~10–30ms | sıcak |
| vektör arama (yüzlerce not) | ~1–5ms | sıcak |
| paketleme | ~1ms | sıcak |
| **sıcak yol toplam** | **<50ms** | her prompt |
| soğuk spawn + model yükle | 1–3sn | **kaçınılan** |
| distill/özet (Ollama 3B) | birkaç sn | arka plan |

Yavaşlığın tek kaynağı soğuk başlatma. Çözüm: **resident sıcak daemon** —
model bir kez yüklenir, sonraki her sorgu sıcak.

---

## 7. Kaynak (RAM) tasarımı

| Bileşen | RAM | Sürekli? |
|---|---|---|
| broker process | ~30–50MB | evet |
| embedding modeli (bge-small ONNX) | ~150–250MB | evet (küçük) |
| sqlite index | birkaç MB (mmap) | evet |
| **broker toplam** | **~250MB** | bir tarayıcı sekmesi |
| Ollama küçük model (3B) | 2–3GB | **HAYIR — sadece distill anında** |

Kademeler:
- **Tier A (minimal, ~50MB):** embedder yok, saf FTS retrieval. Eski makinede bile rahat.
- **Tier B (önerilen, ~250MB):** + resident embedder. İyi ilgililik.
- **Tier C:** büyük reranker — RAM artar, kazanç az → **atla**.

Kural: küçük embedder sıcak kalır, büyük LLM tembel/on-demand. Korkulan 4–8GB
hiçbir zaman sürekli durmaz.

---

## 8. "Recall'a gerek yok" deneyimi

Önce: session başında bir kez recall bloğu; ortada ihtiyaç olursa manuel arama;
MCP kayıtlı değilse hiç. (Bugünkü arıza tam buydu.)

Sonra: her prompt'ta broker ilgili kararları/planı/task'ı sessizce ekler. Sen
"şu UID planına göre devam et" dersin; broker `uid-goc-plani-tam`'ı zaten
bağlama koymuştur. Distiller de yeni kararları arka planda nota çevirir →
hafıza kendi kendini besler.

---

## 9. Teknoloji seçimleri ve gerekçe

| Katman | Seçim | Neden |
|---|---|---|
| Çekirdek | mnemo (mevcut) | hazır, AI-agnostik, markdown taşınır |
| Index | sqlite + FTS5 (+ sqlite-vec) | sıfır sunucu, hızlı, taşınır |
| Embedding | fastembed / bge-small (ONNX) | yerel, hızlı, küçük RAM |
| Kalite | mekanik kurallar (recency/supersede/expire) | LLM yok, ms, bağımlılıksız |
| ~~Yerel LLM~~ | ~~Ollama~~ → **düştü** | mekanik kalite katmanı yeterli (§4.4) |
| Broker | resident Python daemon + localhost API | model sıcak kalır, ön yüz bağımsız |
| Enjeksiyon | Claude Code hook (UserPromptSubmit) | terminal yazmadan çalışır |
| Terminal | Wave fork / Tauri+xterm.js | sıfırdan terminal yazma |

---

## 10. Yol haritası (fazlar)

### Faz 0 — Temizlik + `context` MVP · şimdi
Broker'a geçmeden önce retrieval hipotezini ölç.
- [x] `mnemo context <query>`: MOC + karar/ders/reference özetlerini token bütçesiyle paketle.
- [ ] mnemo MCP server'ı kaydet (`claude mcp add --scope user`).
- [ ] Tool'u yenile: bozuk `mnemofish` kalıntısını sil, repo'dan `0.2.1 + [mcp]` kur.
- [x] `context` benchmark **harness** shipped: `mnemo bench <cases.json>` →
  hit-rate / MRR / mean-recall (`bench.py`). Kalan: 10 gerçek prompt'luk cases dosyasını doldur.
- **Kabul:** manuel arama yapmadan doğru UID/STPM bağlamı geliyor; gürültü ve token bütçesi ölçülüyor.

### Faz 0.5 — Kalite katmanı (supermemory-türevi) · ✅ shipped 2026-06-25
supermemory karşılaştırmasından (§14) çıkan, bizde eksik retrieval kalitesi —
hepsi LLM'siz, 40 test yeşil:
- [x] **Eval harness** (`bench.py`, `mnemo bench`).
- [x] **Recency ağırlığı** — context sıralaması tazelikle harmanlanır.
- [x] **Profile tipi** — statik gerçekler her pakete sabitlenir.
- [x] **Temporal supersession** — `write --supersedes`, `status: superseded`.
- [x] **Ephemeral expire** — eski `note`/`daily` context'ten düşer.
- **Kabul:** baseline'a karşı hit-rate/MRR ölçülebilir; çelişen kararlar otomatik gizlenir.

### Faz 1 — Enjeksiyon / broker kararı · sonra
- [ ] `UserPromptSubmit` hook → önce `mnemo context` çıktısını her prompt'a ekle.
- [ ] Eğer CLI soğuk başlangıcı rahatsız ederse resident broker daemon: `localhost /context`, sıcak embedder, Tier A→B.
- **Kabul:** yeni Claude Code session'ında manuel recall'a gerek yok; daemon sadece ölçüm gerekiyorsa ekleniyor.

### Faz 2 — Librarian (LLM yazma otomasyonu) · ❌ DÜŞTÜ (2026-06-25)
Ollama distiller planı iptal. Çözeceği çekirdek iş (çelişki/eskime) Faz 0.5'te
mekanik olarak çözüldü. Yalnız LLM gerektiren "session → otomatik karar distill"
isteği geri gelirse yeniden değerlendirilir — şimdilik kapsam dışı.

### Faz 3 — Terminal ön yüzü · en son
- [ ] Wave fork / Tauri+xterm.js değerlendir, birini seç.
- [ ] Broker'a bağla; proje/path seçici + hafıza dashboard.
- [ ] Gömülü chat'e doğrudan bağlam enjeksiyonu.
- **Kabul:** terminalde proje aç, AI otomatik hafızalı çalışıyor.

---

## 11. Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Yerel model kötü not seçer → gürültü | ilgililik eşiği + sert token bütçesi; alakasızsa hiç enjekte etme |
| Oto-distill yanlış karar üretir | `status: draft`; mekanik işler (link) otomatik, karar çıkarma onaylı |
| Per-prompt latency | LLM sıcak yolda yok; resident sıcak embedder; cache |
| RAM şişer | büyük LLM on-demand + keep_alive; Tier A fallback |
| Terminal scope patlaması | sıfırdan yazma yok; hazır tabanı çatalla; en son faz |
| Vault gizlilik (private repo) | mnemo zaten private git uyarısı veriyor; broker sadece localhost |

---

## 12. Bugün ne VAR, ne YENİ (dürüst kapsam)

**Var:** vault, sqlite index, embedding alt yapısı (`Embedder`), MCP server
(`serve`), recall hook, proje tespiti, FTS+vec arama, taşınabilirlik (git/zip),
`context` paketi, **+ kalite katmanı** (bench / recency / profile / supersession
/ expire — Faz 0.5, shipped).

**Yeni yazılacak:** resident broker daemon + localhost API, UserPromptSubmit
enjeksiyon hook'u, terminal ön yüzü.

**Düşen:** Ollama librarian (LLM distill) — mekanik kalite katmanı yerine geçti.

---

## 13. Karar bekleyen noktalar

1. **Başlangıç:** Faz 0'a şimdi başlayayım mı (önce 3 fix + broker iskeleti)?
2. **Retrieval kademesi:** ~~Tier A mı Tier B mi?~~ → **KARAR: Tier B**
   (resident embedder, ~250MB, iyi ilgililik). 2026-06-23.
3. ~~**Librarian agresifliği**~~ → kapandı: LLM librarian düştü (§4.4, Faz 2).
4. **Terminal tabanı:** Wave fork mu, Tauri+xterm.js mı? (Faz 3'te netleşir.)

---

## 14. supermemory karşılaştırması (neden evirdik)

[supermemory](https://github.com/supermemoryai/supermemory) (27.5k★) olgun bir
hafıza motoru. İkisini birlikte kullanmak yerine (çift yazım/drift riski), onun
**iyi yaptığı ama bizde eksik** parçaları mnemo'nun kimliğine (markdown + push +
local) uydurarak aldık. Almadıklarımız bilinçli kapsam-dışı.

| supermemory'de güçlü | mnemo'ya nasıl girdi | Durum |
|---|---|---|
| Fact extraction + çelişki çözme (yeni eskiyi geçersiz kılar) | temporal supersession (`--supersedes`, `status`) | ✅ mekanik |
| Auto-expire (alakasız bilgi düşer) | ephemeral expire (`note`/`daily` raf ömrü) | ✅ |
| Profil (statik gerçekler ~50ms) | `profile` tipi, pakete sabit | ✅ |
| Recency-aware retrieval | recency decay ağırlığı | ✅ |
| Benchmark (LongMemEval #1) | `mnemo bench` eval harness | ✅ |
| LLM ile distill | — | ❌ kapsam dışı (mekanik yeterli) |
| Connectors (Gmail/Drive/Notion) | — | ❌ scope patlaması |
| Multimodal (PDF/OCR/video) | — | ❌ kimliğimiz değil |

Korunan ayrım: supermemory Postgres/binary store + LLM kullanır; biz onun
*davranışını* aldık, **store'unu değil** — markdown tek kaynak, LLM sıfır.

---

*Bu rapor konuşmadaki kararların damıtımıdır. Faz 0.5 (kalite katmanı) uygulandı;
sıradaki karar broker daemon (Faz 1) mı, cases dosyası + benchmark mı.*
