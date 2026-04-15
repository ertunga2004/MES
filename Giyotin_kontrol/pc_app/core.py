import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATA_PATH = Path("data/isler.csv")
LOG_DIR = Path("logs")


@dataclass
class GiyotinIslem:
    is_kodu: str
    is_adi: str
    toplam_kesim: int
    mevcut_kesim: int = 0

    def ilerle(self):
        if self.mevcut_kesim < self.toplam_kesim:
            self.mevcut_kesim += 1
            return True
        return False

    def bitti_mi(self):
        return self.mevcut_kesim >= self.toplam_kesim


def isleri_yukle():
    isler = {}
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            kod = row["is_kodu"].strip().upper()
            isler[kod] = {
                "adi": row["is_adi"].strip(),
                "kesim": int(row["kesim_sayisi"])
            }
    return isler


def log_event(session_id: str, event: str, cut_no: int, cut_total: int, extra: str = ""):
    LOG_DIR.mkdir(exist_ok=True)
    fp = LOG_DIR / f"{session_id}.csv"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # ms
    if not fp.exists():
        fp.write_text("timestamp,event,cut_no,cut_total,extra\n", encoding="utf-8")

    with open(fp, "a", encoding="utf-8") as f:
        f.write(f"{ts},{event},{cut_no},{cut_total},{extra}\n")
        f.flush()
