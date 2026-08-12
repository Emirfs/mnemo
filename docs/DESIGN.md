# mnemo — Tasarım Dokümanı

> Çalışma adı: **mnemo** (Mnemosyne — hafıza). Değiştirilebilir.
> Bu dosya iç tasarım/çalışma dokümanıdır (Türkçe). Public README ayrıca İngilizce yazılacak.
> Durum: TASLAK v0.1 — scope dondurma aşaması.

Kişisel, projeler-arası, AI-arası **kalıcı hafıza (persistent memory)** sistemi.
Markdown vault üstünde çalışan bir **MCP memory server** + **CLI** + **Claude Code hook**'ları.

---

## 1. Problem

Mevcut hafıza araçları (ör. claude-mem) **depolamayı** çözüyor ama **geri-çağırmayı (retrieval)** çözmüyor.

> Yaşanan: "Kaydet" deniyor, kaydediliyor — ama AI doğru anıyı doğru anda **okumuyor**.

Asıl darboğaz: bilgiyi yazmak değil, **ilgili alt kümeyi doğru anda modelin context'ine otomatik enjekte etmek.**

İkinci problem: bilgi büyüdükçe token tüketimi ve bilgi kalabalığı artar. Her şeyi yüklemek sürdürülemez.

---

## 2. Temel İlkeler

1. **Retrieval-first.** Sistem "yazma"ya değil, "doğru anıyı otomatik getirme"ye göre tasarlanır.
2. **Push > Pull.** MCP tool (pull) modelin çağırmasını bekler — claude-mem'in patladığı yer. Gerçek otomasyon **hook** (push) ile: AI sormadan ilgili not context'e enjekte edilir.
3. **Vault = tek kaynak.** Markdown dosyalar tek gerçek. Index (sqlite/embedding) türetilmiştir, her an silinip yeniden üretilebilir.
4. **Sadece türetilemeyeni sakla.** Dosya ağacı/fonksiyon imzaları AI tarafından bulunabilir → saklama. Kararlar, ilişkiler, sözleşmeler, hatalar, niyet → sakla.
5. **Harita önce, düğüm sonra.** Token'ı sabit tutmak için: önce küçük index (MOC) yüklenir, sadece ilgili atomik not genişletilir. Asla "her şey".
6. **Atomik notlar.** Bir not = bir karar/gerçek/hata. Küçük → tek tek ucuz yüklenir, çakışma minimum, embedding chunking gereksiz.

### Türetilebilir vs türetilemez

| AI kendi bulabilir (SAKLAMA) | AI bulamaz (SAKLA) |
|---|---|
| Dosya ağacı (`glob`) | Topoloji: ne nereye konuşuyor |
| Vendor kod (HAL/CMSIS, node_modules) | Ortak protokol/sözleşmeler |
| Fonksiyon imzaları | Neden bu karar alındı |
| Hangi dosya var | Şu an ne yapılıyor / gotcha / hatalar |

---

## 3. Mimari

**Çekirdek kütüphane + iki ön-yüz.** Bu ayrım belkemiğidir — auto-recall'ı mümkün kılar.

```
            ┌──────────────────────────────────────────┐
            │  Vault (markdown + frontmatter)          │  ← tek kaynak, Obsidian'da da düzenlenir
            └───────────────────┬──────────────────────┘
                                │ parse (incremental, mtime/hash)
                     ┌──────────▼───────────┐
                     │  ÇEKİRDEK LİB        │  index.sqlite (FTS5 + vektör)
                     │  parse / index /     │  ← türetilmiş, .gitignore, rebuild
                     │  search / write      │
                     └─────┬───────────┬────┘
              ┌────────────▼──┐    ┌───▼─────────────────┐
              │  CLI ön-yüz    │    │  MCP ön-yüz          │
              │  (PUSH)        │    │  (PULL)              │
              │  Claude hook   │    │  tüm MCP-uyumlu AI   │
              │  oturum başı   │    │  konuşma içi tool    │
              │  recall enjekte│    │  çağrısı             │
              └────────────────┘    └─────────────────────┘
```

- **Çekirdek lib:** parse + index + search + write. Tek mantık burada.
- **CLI ön-yüz:** hook'lardan çağrılır (push). Oturum başında ilgili MOC + top-N notu basıp context'e enjekte eder. `mnemo search/write/init/sync/...`.
- **MCP ön-yüz:** aynı çekirdeği MCP tool'ları olarak sunar → Claude Code, Cursor ve diğer MCP istemcileri aynı aramayı kullanır.

---

## 4. Vault Yapısı

Vault düz bir klasör (= private GitHub reposu). Önerilen layout:

```
my-memory/                    ← private repo
├── daily/                    günlük notlar, todo, "bugün ne yaptım"
│   └── 2026-06-23.md
├── projects/
│   └── <proje>/
│       ├── _moc.md           proje haritası (Map of Content) — index notu
│       └── <atomik>.md       tek karar/gerçek
├── lessons/                  hatalar, dersler (tag'le retrieval)
├── protocol/                 teknik sözleşmeler (ör. RF v2)
├── reference/                kalıcı bilgi (URL, dashboard, ticket)
├── .gitignore                index.sqlite + .cache hariç
└── .mnemo/                   (gitignore) index.sqlite, embedding cache
```

`projects/`, `lessons/` vb. **sabit değil** — kullanıcı kendi taksonomisini kurabilir; sistem `type` frontmatter'a göre çalışır, klasör adına değil.

---

## 5. Not Şeması (frontmatter)

Her not = markdown + YAML frontmatter:

```markdown
---
id: 20260623-rf-uid-sequential        # kararlı kimlik (tarih-slug)
type: decision                         # decision | lesson | daily | project | reference | note
title: RF güncellemesi sıralı yapılır
project: stm32-rf-ota                  # opsiyonel
tags: [rf, protocol, stm32]
created: 2026-06-23
updated: 2026-06-23
summary: Cihazlar tek tek güncellenir; eşzamanlı değil — sistem kilitlenmesini önler.
links: [20260623-rf-uid-identity]      # [[wikilink]] de desteklenir
---

Sıralı güncelleme: id1 biter, id2 başlar. Avantaj: tüm cihazlar aynı anda
bootloader'a düşmez, sistem ayakta kalır...
```

- `summary` zorunlu ve **kısa** → index/MOC bunu gösterir, gövdeyi değil. Token disiplini buradan gelir.
- `type` retrieval filtresini sağlar (teknik görevde `daily` notları boğmaz).
- `links` ilişki grafiğini kurar (MOC + backlink + AI traversal).

---

## 6. MOC (Map of Content)

`_moc.md` = bir projenin/konunun **haritası**. Atomiklere link + tek satır özet.

```markdown
---
type: project
title: STM32 RF OTA — MOC
project: stm32-rf-ota
---
# STM32 RF OTA

## Kararlar
- [[20260623-rf-uid-identity]] — kimlik = 96-bit STM32 UID, hash yok
- [[20260623-rf-uid-sequential]] — güncelleme sıralı, eşzamanlı değil

## Bileşenler
- Sender STM32 (RF gateway), PC Uploader (Python/Qt), MobileUploader (Flutter)
- Alıcılar: stpm, stpm_fc (bootloader) + app'leri

## Açık işler
- [ ] DISCOVER_ACK 7→18 byte (UID) geçişi
```

Recall akışı: **MOC önce yüklenir** → AI ilgili linki görür → sadece o atomik notu `get` ile açar. Vault 10.000 nota çıksa bile bir görev = 1 MOC + birkaç atomik.

---

## 7. Index Katmanı

- **Store:** vault markdown. **Index:** `.mnemo/index.sqlite` (atılabilir).
- **Lexical:** SQLite **FTS5** (keyword/tag araması, deterministik, model gerektirmez).
- **Semantic:** lokal embedding (sentence-transformers) → `sqlite-vec` ile vektör araması (paraphrase/eşanlam yakalar).
- **Hybrid:** FTS5 + vektör sonuçları birleştirilir (rerank).
- **Incremental:** dosya başına mtime/hash → sadece değişeni yeniden parse+embed. Tüm vault'u her seferinde işleme yok.
- **Embedding lokal:** API yok, offline, gizli. (API opsiyonel eklenebilir.)

---

## 8. Retrieval (token disiplini)

`search` **özet + path + skor** döndürür, **tam gövde değil.** Map-then-expand sözleşme seviyesinde gömülü.

```
search("rf güncelleme sırası", type=decision, k=5)
  → [{id, title, summary, path, score}, ...]   # ~5 satır, ucuz
get(path)                                        # sadece gerekirse tam gövde
```

Böylece bilgi büyüdükçe görev başına token **sabit** kalır.

---

## 9. MCP Tool API

| Tool | Girdi | Çıktı | Not |
|---|---|---|---|
| `memory_search` | query, type?, project?, tags?, k=5 | özet+path+skor listesi | gövde DÖNMEZ |
| `memory_get` | path/id | tam not | on-demand |
| `memory_moc` | project | proje haritası | "harita" |
| `memory_write` | type, title, body, tags, links | yeni/güncellenmiş not | **yazmadan-önce-ara** (dedup) |
| `memory_link` | id_a, id_b | — | düğümleri bağla |

Notlar MCP **resource** olarak da sunulabilir (opsiyonel).

---

## 10. CLI Komutları

| Komut | İş |
|---|---|
| `mnemo init [--remote <github-url>]` | vault'u (git reposu olarak) kur |
| `mnemo reindex` | index'i sıfırdan kur (taşıma sonrası) |
| `mnemo search <query> [--type --project -k]` | hook/manuel arama |
| `mnemo write ...` | not ekle (dedup'lı) |
| `mnemo recall [--project]` | oturum-başı enjeksiyon bloğu üret (hook bunu basar) |
| `mnemo sync` | git pull + push |
| `mnemo clone <github-url>` | yeni makine: klonla + reindex |
| `mnemo export <file>` / `import <file>` | tek-parça taşıma (Drive vb.) |
| `mnemo compact` | dedup/çürüme temizliği |

---

## 11. Hook Akışı (Claude Code — PUSH)

Auto-recall'ı mümkün kılan kısım. `settings.json` hook'ları:

- **SessionStart:** `mnemo recall --project <cwd>` → ilgili MOC + son kararlar/dersler context'e enjekte edilir. AI **sormadan** geçmişi bilerek başlar.
- **UserPromptSubmit (opsiyonel):** prompt'tan keyword/embedding → top-N not enjekte (göreve özel recall).
- **Stop / SessionEnd:** oturumdan karar/hata/yapılanı çıkar → `mnemo write` (auto-capture, v3).

> Bu, claude-mem'in çözemediği "okuma döngüsü"nü kapatır.

---

## 12. Cross-AI

- **MCP-uyumlu** (Claude Code, Cursor, ...): aynı MCP server'a bağlanır → aynı arama/recall.
- **MCP-suz** (düz ChatGPT web vb.): MCP kullanamaz → ya `mnemo export` ile parça yapıştırma, ya vault'u elle okutma. Dürüst sınır.
- Store evrensel (markdown), retrieval-wiring araç-başına.

---

## 13. Taşınabilirlik — GitHub omurgası

- **Vault = private GitHub reposu.** Sadece markdown commit'lenir; `index.sqlite` + embedding cache `.gitignore`.
- **Yeni makine / yeni AI:** `mnemo clone <github-url>` → klonla + reindex → her şeyi bilerek gelir. ("Hafızayı çek.")
- **Avantaj:** versiyonlu bilgi (ne zaman öğrendim/değiştirdim), bedava sync, merge, yedek.
- **Drive/Dropbox:** opsiyonel; vault düz klasör olduğu için çalışır ama versiyon/merge vermez. `export/import` tek-parça taşıma için.
- Atomik notlar → git merge çakışması minimum.

---

## 14. Çürüme Önleme (claude-mem'in ölüm sebebi)

- **Yazmadan-önce-ara:** `write` önce benzer not arar; varsa yeni açmaz → günceller/ekler.
- **`compact`:** periyodik dedup + ölü link temizliği.
- **summary zorunlu:** her not özetlenebilir olmalı; özetlenemeyen not = kötü not.

---

## 15. Gizlilik / Güvenlik

- **İki repo, karıştırma:**
  - **PUBLIC** (OSS): `mnemo` yazılımı. Generic, vault-path config, kişisel veri YOK.
  - **PRIVATE**: kullanıcının vault'u (notlar, kararlar, hatalar).
- Araç remote'un **public** göründüğünü sezerse uyarır (notların yanlışlıkla yayınlanmasını önle).
- Lokal embedding → veri makineden çıkmaz (API opsiyonel ve açıkça opt-in).

---

## 16. Teknoloji

- **Dil:** Python. Dağıtım: `uvx` (npx kadar kolay).
- **Bağımlılıklar:** `mcp` (SDK), `python-frontmatter`, `sentence-transformers`, `sqlite-vec`, SQLite FTS5 (stdlib).
- **Store:** vault markdown + `.mnemo/index.sqlite` (sidecar, atılabilir).

---

## 17. İnşa Yol Haritası (bağımlılık sırası — hepsi tam sürümde)

| Faz | Çıktı | Kanıt | Durum |
|---|---|---|---|
| **F1 — Çekirdek** | parse + frontmatter + FTS5 + incremental index | `search` doğru notu döndürür | ✅ |
| **F2 — CLI + Hook** | `recall/search/write` + Claude SessionStart hook (push) | AI sormadan geçmişi bilerek başlar | ✅ |
| **F3 — MCP** | `memory_search/get/moc/write` server | Cursor/Claude aynı vault'ta arar | ✅ |
| **F4 — Taşıma** | `init/sync/clone/export/import` (GitHub) | yeni makinede klonla+reindex çalışır | ✅ |
| **F5 — Semantic + daily** | fastembed+sqlite-vec hybrid (RRF), içerik dedup, `daily` journaling | paraphrase araması FTS'in kaçırdığını bulur | ✅ |

F2 sonunda **okuma döngüsü kapandı** → claude-mem'i geçer. 24 test geçiyor.

**Embedding backend kararı (çözüldü):** fastembed (ONNX) + `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, çok-dilli, Türkçe). torch yok → hafif/hızlı cold-start. SessionStart hook (`recall`) embedding YÜKLEMEZ (sadece SQL) → hızlı kalır; model yalnız `search/serve/write/reindex`'te lazy yüklenir.

**Sonraki (F5+ / opsiyonel):** transcript'ten otomatik yakalama (rot riski yüksek — bilerek ertelendi; şimdilik recall footer modeli `memory_write`'a yönlendiriyor), `compact` (dedup/ölü-link temizliği), MOC yarı-otomatik üretimi.

---

## 18. Kararlar + Açık Sorular

### Verilen kararlar (2026-06-23)
1. **Embedding modeli:** hız + kararlılık öncelik. Notlar **Türkçe** → çok-dilli MiniLM (`paraphrase-multilingual-MiniLM-L12-v2`) varsayılan. FTS5 keyword zaten dilden bağımsız; embedding katmanı çok-dilli.
2. **Proje tespiti:** **git remote slug → yoksa klasör adı** fallback.
3. **İsim:** `mnemo` kalır.

### Açık (sonra)
- **Auto-capture tetiği:** her oturum sonu mu, commit'te mi, manuel onaylı mı? (F5)
- **MOC üretimi:** elle mi, yarı-otomatik mi (atomiklerden link toplama)? (F3+)
- **Embedding backend:** sentence-transformers (torch, ağır) vs ONNX/fastembed (hızlı cold-start — hook için önemli). F1'de modül pluggable; dağıtımda ONNX'e geçiş değerlendirilecek.

---

> Sonraki adım: bu DESIGN onaylanınca → public repo iskeleti + `pyproject.toml` + F1 çekirdek.
