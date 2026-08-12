# AGENTS.md

<!-- ghd:core:start -->
<!-- Emirfs/ghd tarafindan uretildi. Elle duzenleme; kaynak: rules/GITHUB-RULES.md -->
GitHub islemlerinde `Emirfs/ghd` reposundaki `rules/GITHUB-RULES.md` kurallari gecerlidir.
<!-- ghd:core:end -->

## Bu repo

<!-- ghd:repo:start -->
- **Ne yapar:** Markdown vault uzerinde kalici, tasinabilir ve AI'lar arasi hafiza saglar.
- **Tip:** python
- **Kurulum:** `uv sync --extra dev`
- **Derle:** `uv build`
- **Test:** `uv run pytest -q`
- **Calistir:** `uv run mnemo --help`

### Dizin haritasi

Dizin haritasi `CONTEXT.md`'de. Bir dosyayi acmadan once oraya bak.

### Notlar

- `.mnemo/` turetilmis index ve cache durumudur; kaynak degildir, commitlenmez.
- Public arac reposuna kisisel vault icerigi ekleme.
<!-- ghd:repo:end -->
