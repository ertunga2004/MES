# Docs / Archive

Bu klasör, MES projesinde artık aktif olmayan veya daha güncel dokümanlar tarafından kapsanmış eski plan ve yol haritası dosyalarını içerir.

## Amaç

Buradaki dosyalar geliştirme sürecinin tarihsel izini korumak amacıyla saklanmaktadır. **Aktif mimari kaynak değildir.**

## Kritik Kurallar

- Bu klasördeki dosyalar kod kararına dayanak yapılmamalıdır.
- Aktif mimari hafıza ve çalışma kuralları için `docs/agent_memory/` klasörü kullanılmalıdır.
- Aktif PostgreSQL geçiş dokümanları için `docs/postgres/` klasörü kullanılmalıdır.

## Alt Klasörler

### `legacy_plans/`

Eski yol haritası ve aşama planlarını içerir. Bu dosyalar, `docs/agent_memory/` içindeki hafıza dokümanları tarafından kapsanmış ve superseded olmuştur.

| Dosya | Neden arşivlendi |
|---|---|
| `roadmap.md` | Proje gelişim hedefleri ve kısa/orta/uzun vade planı. `agent_memory/01_current_progress.md` ve `09_antigravity_handoff.md` tarafından kapsanmıştır. |

## Aktif Kaynaklar İçin Okuma Sırası

1. `docs/agent_memory/README.md`
2. `docs/agent_memory/00_masterplan.md`
3. `docs/agent_memory/08_guardrails_and_do_not_touch.md`
4. `docs/agent_memory/09_antigravity_handoff.md`
