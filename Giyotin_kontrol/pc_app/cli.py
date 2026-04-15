import time
from datetime import datetime

from core import isleri_yukle, GiyotinIslem, log_event
from serial_bridge import NanoGiyotin


PORT = "COM12"
BAUD = 9600


def main():
    print("=== GIYOTIN KONTROL (NANO / COM12) ===\n")

    # --- İşleri yükle ---
    isler = isleri_yukle()
    if not isler:
        print("HATA: data/isler.csv bulunamadi veya bos!")
        return

    print("Mevcut isler:")
    for kod, info in isler.items():
        print(f"  {kod} - {info['adi']} ({info['kesim']} kesim/adet)")

    # --- Kullanıcı seçimleri ---
    is_kodu = input("\nIs kodu sec: ").strip().upper()
    if is_kodu not in isler:
        print("HATA: Gecersiz is kodu!")
        return

    try:
        adet = int(input("Kac adet yapilacak: ").strip())
        if adet <= 0:
            raise ValueError
    except ValueError:
        print("HATA: Adet pozitif bir tam sayi olmali!")
        return

    toplam_kesim = adet * isler[is_kodu]["kesim"]
    islem = GiyotinIslem(is_kodu, isler[is_kodu]["adi"], toplam_kesim)

    session_id = f"{is_kodu}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\nSESSION: {session_id}")
    print(f"IS: {islem.is_adi}")
    print(f"ADET: {adet}")
    print(f"TOPLAM KESIM: {toplam_kesim}\n")

    print("Operator: Nano uzerindeki BUTONA basarak kesim yaptir.")
    print("PC eventleri loglayacak. (CTRL+C = acil cikis)\n")

    # --- Nano'ya bağlan ---
    try:
        nano = NanoGiyotin(port=PORT, baud=BAUD)
    except Exception as e:
        print("HATA: Nano baglanamadi:", e)
        return

    # --- İş başlangıcı: DISARM -> ARM ---
    try:
        nano.write_cmd("DISARM")
        time.sleep(0.1)
        nano.write_cmd("ARM")
    except Exception as e:
        print("HATA: Nano'ya komut gonderilemedi:", e)
        nano.close()
        return

    # --- Log başlangıç ---
    log_event(session_id, "JOB_START", 0, toplam_kesim, extra=f"is={is_kodu};adet={adet};port={PORT}")

    job_start_t = time.monotonic()

    cut_start_t = None
    cut_durations = []  # CUT_START -> CUT_DONE süreleri

    last_cut_up_t = None
    operator_durations = []

    try:
        while not islem.bitti_mi():
            line = nano.read_line()
            if not line:
                continue

            now = time.monotonic()

            if line == "BTN_PRESS":
                # OPERATÖR SÜRESİ
                if last_cut_up_t is not None:
                    op_time = now - last_cut_up_t
                    operator_durations.append(op_time)

                    avg_op = sum(operator_durations) / len(operator_durations)
                    mn_op = min(operator_durations)
                    mx_op = max(operator_durations)

                    print(
                        f"Operatör süresi: {op_time:.2f}s "
                        f"| ort: {avg_op:.2f}s | min: {mn_op:.2f}s | max: {mx_op:.2f}s"
                    )

                    log_event(
                        session_id,
                        "OPERATOR_TIME",
                        islem.mevcut_kesim + 1,
                        islem.toplam_kesim,
                        extra=f"operator_sec={op_time:.3f};avg_op_sec={avg_op:.3f};min_op_sec={mn_op:.3f};max_op_sec={mx_op:.3f}"
                    )

                log_event(session_id, "BTN_PRESS", islem.mevcut_kesim + 1, islem.toplam_kesim)

            elif line == "CUT_START":
                cut_start_t = now
                log_event(session_id, "CUT_START", islem.mevcut_kesim + 1, islem.toplam_kesim)

            elif line == "CUT_UP":
                last_cut_up_t = now
                log_event(session_id, "CUT_UP", islem.mevcut_kesim + 1, islem.toplam_kesim)

            elif line == "CUT_DONE":
                dur = None
                if cut_start_t is not None:
                    dur = now - cut_start_t
                    cut_durations.append(dur)
                    cut_start_t = None

                islem.ilerle()

                if dur is not None:
                    avg = sum(cut_durations) / len(cut_durations)
                    print(f"Kesim süresi: {dur:.2f}s | ort: {avg:.2f}s")

                    log_event(
                        session_id,
                        "CUT_DONE",
                        islem.mevcut_kesim,
                        islem.toplam_kesim,
                        extra=f"cut_sec={dur:.3f};avg_cut_sec={avg:.3f}"
                    )

            else:
                # Bilinmeyen satırlar boşa gitmesin diye loglayalım
                log_event(session_id, "RAW", islem.mevcut_kesim, islem.toplam_kesim, extra=line)

        # --- İş bitti ---
        elapsed = time.monotonic() - job_start_t
        try:
            nano.write_cmd("DISARM")
        except Exception:
            pass

        log_event(session_id, "JOB_DONE", islem.mevcut_kesim, islem.toplam_kesim, extra=f"elapsed_sec={elapsed:.3f}")

        print("\n🎉 IS TAMAMLANDI")
        print(f"Toplam gecen sure: {elapsed:.1f} saniye ({elapsed/60:.2f} dk)")

        if cut_durations:
            avg = sum(cut_durations) / len(cut_durations)
            mn = min(cut_durations)
            mx = max(cut_durations)
            print(f"Kesim istatistikleri: ort={avg:.2f}s | min={mn:.2f}s | max={mx:.2f}s | adet={len(cut_durations)}")

        print(f"Log: logs/{session_id}.csv")

    except KeyboardInterrupt:
        elapsed = time.monotonic() - job_start_t
        try:
            nano.write_cmd("DISARM")
        except Exception:
            pass
        log_event(session_id, "JOB_ABORT", islem.mevcut_kesim, islem.toplam_kesim, extra=f"elapsed_sec={elapsed:.3f}")

        print("\n⚠ ACIL CIKIS (CTRL+C)")
        print(f"Durum: {islem.mevcut_kesim}/{islem.toplam_kesim}")
        print(f"Gecen sure: {elapsed:.1f} saniye")
        print(f"Log: logs/{session_id}.csv")

    finally:
        nano.close()


if __name__ == "__main__":
    main()
