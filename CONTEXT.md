# mnemo — proje haritasi
Durum: BEKLEMEDE — 2026-11-18'den beri ortak hafiza `~/GitHub/araclar/hafiza`
kasasinda (MCP `hafiza`); bu arac yeni iste kullanilmiyor.
Yigin: Python >= 3.10, hatchling ile paketlenir. PyPI adi `mnemofish`
(surum 0.2.1, MIT). Dagitim: CLI + MCP sunucusu.

Markdown vault uzerinde kalici, tasinabilir ve AI'lar arasi hafiza araci.
Iki yol vardir:
- **PUSH**: `SessionStart` hook'u ilgili notlari daha ilk mesajdan once
  baglama enjekte eder (auto-recall).
- **PULL**: MCP sunucusu, MCP konusabilen her AI'in ayni vault'ta arama
  yapmasini saglar.

Bu depo **aractir**; kisisel vault icerigi `../mnemo-vault` deposunda durur.

## SU AN
Canli dosya: yok.
Nerede kaldik: Ortak hafiza `hafiza` kasasina tasindi; mnemo bekletiliyor.
Siradaki: - [ ] Arsivlenip arsivlenmeyecegine karar ver.

Dal: `main`. Son commit tarihi icin `git log -1`.

## Calistirma
| Komut | Ne yapar |
|---|---|
| `uv sync --extra dev` | Gelistirme ortamini kurar |
| `uv run mnemo --help` | CLI'yi calistirir (`mnemo` ve `mnemofish` ayni giris) |
| `uv run pytest -q` | Test paketini kosar |
| `uv build` | Dagitim paketini uretir |

Opsiyonel ekstralar: `embed` (fastembed + sqlite-vec), `mcp` (MCP sunucusu).

## Dosyalar
| Dosya | Is |
|---|---|
| `src/mnemo/cli.py` | Komut satiri girisi |
| `src/mnemo/server.py` | MCP sunucusu (PULL yolu) |
| `src/mnemo/context.py` | Oturum baglami uretimi (PUSH yolu) |
| `src/mnemo/recall.py` | Auto-recall mantigi |
| `src/mnemo/search.py`, `index.py` | Arama ve turetilmis SQLite indeksi |
| `src/mnemo/embed.py` | Vektor gomme (opsiyonel `embed` ekstrasi) |
| `src/mnemo/vault.py`, `note.py`, `writer.py` | Vault okuma/yazma, not modeli |
| `src/mnemo/librarian.py` | Vault bakim/duzenleme akisi (bkz. `docs/librarian.md`) |
| `src/mnemo/bridge.py` | Diger AI araclarina kopru (bkz. `docs/bridge.md`) |
| `src/mnemo/telegram.py` | Telegram entegrasyonu (bkz. `docs/telegram.md`) |
| `src/mnemo/research.py` | Arastirma notu akisi |
| `src/mnemo/executor.py`, `approval.py` | Komut yurutme ve onay katmani |
| `src/mnemo/autostart.py` | Otomatik baslatma kurulumu |
| `src/mnemo/portability.py` | Vault tasinabilirligi |
| `src/mnemo/daily.py` | Gunluk kayitlar |
| `src/mnemo/feedback.py`, `bench.py` | Geri bildirim ve olcum |
| `src/mnemo/config.py` | Ayarlar |
| `hooks/` | `SessionStart` hook ornekleri ve ayarlari |
| `tests/` | pytest paketi |
| `docs/DESIGN.md`, `SISTEM-PLANI.md` | Tasarim ve sistem plani |
| `docs/mcp.md`, `bridge.md`, `librarian.md`, `telegram.md` | Alt sistem dokumanlari |
| `pyproject.toml` | Paket metadata, bagimliliklar, CLI giris noktalari |
| `.mnemo/` | Turetilmis SQLite index ve cache — commitlenmez |
| `AGENTS.md` / `CLAUDE.md` | Depo calisma kurallari |

## Bagimliliklar
- Zorunlu: `python-frontmatter`.
- `embed` ekstrasi: `fastembed`, `sqlite-vec`.
- `mcp` ekstrasi: `mcp>=1.2.0,<2`.
- Vault: `../mnemo-vault` (kisisel, ayri depo).

## Degismezler
- **Markdown vault kaynak gercektir**; `.mnemo/` yalniz turetilmis durumdur ve
  her an yeniden uretilebilir.
- Arama varsayilan olarak **ozet ve path** dondurur; tam govde ancak acik
  istekle yuklenir.
- Public arac reposu ile kisisel/private vault icerigi karistirilmaz.

## Dikkat
- PyPI paketi `mnemofish`, modul adi `mnemo`. Iki CLI girisi de ayni
  fonksiyona baglidir.
- Kisisel not, vault yolu veya API anahtari bu depoya commit edilmez.
