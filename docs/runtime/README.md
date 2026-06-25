# Runtime Docs

Bu klasor calisma, saha test, MQTT, donanim ve MVP runbook dokumanlarini tutar.

## Ana Dokumanlar

- [Field Test Plan](field-test-plan.md)
- [Hardware Notes](hardware.md)
- [MQTT Topics](mqtt-topics.md)
- [MVP Runbook](MVP_RUNBOOK.md)
- [Tablet Plan](tablet_plan.md)

## Bu Klasorde Ne Yapilmamali?

- Runtime kodu burada degistirilmez; bu klasor sadece dokuman alanidir.
- Docker, DB migration veya mes_web davranis degisikligi bu cleanup fazinda yapilmamali.
- BOM/BOP veya MESQL schema karar notlari runtime dokumanlarina karistirilmamali.

## Ilgili Klasorler

- [Architecture](../architecture/README.md)
- [MESQL](../mesql/README.md)
- [Docs Index](../INDEX.md)
