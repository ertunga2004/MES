import cv2
import numpy as np

def nothing(x):
    pass

# Laptobun varsayılan web kamerasını başlat (Genelde 0'dır)
cap = cv2.VideoCapture(0)

# Trackbar'lar için ayar penceresi oluştur
cv2.namedWindow("Ayarlar", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Ayarlar", 400, 250)

# HSV Alt ve Üst limitleri için kaydırma çubukları
cv2.createTrackbar("H_Min", "Ayarlar", 0, 179, nothing)
cv2.createTrackbar("S_Min", "Ayarlar", 0, 255, nothing)
cv2.createTrackbar("V_Min", "Ayarlar", 0, 255, nothing)
cv2.createTrackbar("H_Max", "Ayarlar", 179, 179, nothing)
cv2.createTrackbar("S_Max", "Ayarlar", 255, 255, nothing)
cv2.createTrackbar("V_Max", "Ayarlar", 255, 255, nothing)

print("Sistem çalışıyor... Çıkmak için 'q' tuşuna basın.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Kameradan görüntü alınamadı!")
        break

    # Bilgisayar kamerası genelde aynalı (ters) gösterir, düzeltmek için:
    frame = cv2.flip(frame, 1)

    # Görüntüyü renk ayrımı için HSV formatına çevir
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Trackbar'lardan anlık değerleri oku
    h_min = cv2.getTrackbarPos("H_Min", "Ayarlar")
    s_min = cv2.getTrackbarPos("S_Min", "Ayarlar")
    v_min = cv2.getTrackbarPos("V_Min", "Ayarlar")
    h_max = cv2.getTrackbarPos("H_Max", "Ayarlar")
    s_max = cv2.getTrackbarPos("S_Max", "Ayarlar")
    v_max = cv2.getTrackbarPos("V_Max", "Ayarlar")

    lower_bound = np.array([h_min, s_min, v_min])
    upper_bound = np.array([h_max, s_max, v_max])

    # Sadece seçili renk aralığını beyaza, gerisini siyaha çeviren maske
    mask = cv2.inRange(hsv, lower_bound, upper_bound)

    # Ufak tefek parazitleri (gürültüleri) temizlemek için morfolojik işlem
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.erode(mask, kernel)
    mask = cv2.dilate(mask, kernel)

    # Beyaz alanların (kutuların) dış hatlarını (konturlarını) bul
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Sadece belirli bir büyüklükten büyük olanları kutu olarak kabul et (Gürültüyü ele)
        if area > 1000:
            # Kutuyu içine alan en küçük dikdörtgeni hesapla
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Orijinal görüntü üzerine yeşil bir dikdörtgen çiz
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Geometrik merkez (Centroid) hesaplama (Robot kol için bu X ve Y lazım olacak)
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Merkeze kırmızı bir nokta koy
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                
                # Koordinatları ekrana yazdır (Örn: X:320 Y:240)
                cv2.putText(frame, f"X:{cx} Y:{cy}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    # Görüntüleri ekrana bas
    cv2.imshow("Orijinal Kamera", frame)
    cv2.imshow("Renk Maskesi", mask)

    # 'q' tuşuna basılırsa çık
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()