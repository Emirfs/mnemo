# CONTEXT

`mnemo` - markdown vault uzerinde kalici, tasinabilir ve AI'lar arasi hafiza araci. Bir dosyayi acmadan once bu haritaya bak.

**Tip:** python

## Harita

| Yol | Ne var |
|---|---|
| `src/mnemo/` | Core library, CLI, index/search, MCP, bridge ve entegrasyon kodu. |
| `tests/` | pytest test paketi. |
| `hooks/` | SessionStart hook ornekleri ve ayarlari. |
| `docs/` | Tasarim, mimari ve entegrasyon dokumanlari. |
| `pyproject.toml` | Paket metadata, bagimliliklar ve CLI entry point'leri. |
| `.mnemo/` | Turetilmis SQLite index ve cache; yeniden uretilebilir, commitlenmez. |

## Degismezler

- Markdown vault kaynak gercektir; `.mnemo/` yalniz turetilmis durumdur.
- Arama varsayilan olarak ozet ve path dondurur; tam govde ancak acik istekle yuklenir.
- Public arac reposu ile kisisel/private vault icerigi karistirilmaz.
