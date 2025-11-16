import requests
import os
import time
import random
import re 
from bs4 import BeautifulSoup 
from tqdm import tqdm 
from concurrent.futures import ThreadPoolExecutor, as_completed # Paralel işleme için yeni modüller

# --- AYARLANABİLİR PARAMETRELER ---

MAX_WORKERS = 10  # 🌟 Eş zamanlı çalışacak iş parçacığı (istek) sayısı. Hız burada belirlenir.
DELAY_SECONDS = 2 # 🌟 Her bir iş parçacığı (worker) bekleme süresini korur.
PROXY_FILE = "proxy.txt"
FAILED_ID_FILE = "failed_ids.txt" 
OUTPUT_TXT_FILE = "temiz_rapor_ozetleri.txt" 
# URL'ler ve HTTP ayarları aynı kalır...
# ... (URL_PREFIX, URL_SUFFIX, COOKIES, HEADERS tanımları önceki koddan alınmıştır)

# --- URL, COOKIES, HEADERS (Önceki koddan kopyalayın) ---
URL_PREFIX = "https://vp.golfdondurma.com.tr/SAASReport/ReportView.aspx?CubeReportId=1013829&Values=2;(-1,"
URL_SUFFIX = ")|5;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;|;&RoleId=110628056449&LanguageId=1&UserId=114737182451&ReportTypeId=1&RW=1013832&CL=&DT=1163963292&Mode=ExportToText&Token=47d91344-f898-4996-80a7-788a4ec4f2d9"
COOKIES = {
    "_ga": "GA1.1.383992402.1742082046",
    "_ga_PESWVXLKNX": "GS1.1.1744028568.3.0.1744028568.60.0.0",
    "ASP.NET_SessionId": "fb1eohea3lhixihltffm0lrl"
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari537.36",
    "Referer": "https://vp.golfdondurma.com.tr/Report/reportcubeview2.aspx" 
}
# --- YARDIMCI VE LOGLAMA FONKSİYONLARI ---

def load_proxies(file_path):
    # (Bu fonksiyon aynı kalır, önceki koddan kopyalayın)
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r') as f:
        proxies = [line.strip() for line in f if line.strip()]
    return proxies

def log_failed_id(id_value, reason, proxy=None):
    # (Bu fonksiyon aynı kalır, önceki koddan kopyalayın)
    proxy_info = f" | Proxy: {proxy}" if proxy else ""
    with open(FAILED_ID_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{id_value};{reason}{proxy_info}\n")

def get_user_inputs():
    # (Bu fonksiyon aynı kalır, önceki koddan kopyalayın)
    while True:
        try:
            start_id_str = input("Lütfen taramaya başlayacağınız İLK ID numarasını girin (Örn: 110618401108): ")
            start_id = int(start_id_str)
            
            count_str = input("Lütfen kaç adet ardışık ID taranacağını girin (Örn: 100): ")
            count = int(count_str)
            
            if start_id < 0 or count <= 0:
                print("Hata: ID ve adet pozitif sayı olmalıdır.")
                continue
            
            return start_id, count
        except ValueError:
            print("Hata: Lütfen geçerli bir sayısal değer girin.")
        except KeyboardInterrupt:
            print("\nİşlem kullanıcı tarafından iptal edildi.")
            exit()

# --- TEMEL İŞ PARÇACIĞI FONKSİYONU ---

def process_id(current_id, proxies_list):
    """Tek bir ID'yi işleyen, istek gönderen ve sonucu döndüren fonksiyon."""
    
    full_url = f"{URL_PREFIX}{current_id}{URL_SUFFIX}"
    
    # Proxy seçimi
    selected_proxy = None
    proxies_dict = None
    if proxies_list:
        selected_proxy = random.choice(proxies_list)
        proxies_dict = {
            "http": f"http://{selected_proxy}",
            "https": f"http://{selected_proxy}" 
        }

    try:
        response = requests.get(
            full_url, 
            headers=HEADERS, 
            cookies=COOKIES, 
            proxies=proxies_dict,
            timeout=15 
        )
        
        # İstekler arasında bekleme süresi burada uygulanır.
        time.sleep(DELAY_SECONDS) 

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            distributor_tag = soup.find('td', class_='rowHeader0')
            
            cleaned_text = ""
            if distributor_tag:
                raw_text = distributor_tag.get_text()
                cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
            
            if cleaned_text:
                output_line = f"{current_id};{cleaned_text}\n"
                # Başarılı sonuçları döndür
                return 'SUCCESS', output_line
            else:
                return 'FAILED', (current_id, "İçerik Etiketi Bulunamadı (Oturum Sorunu/Geçersiz ID)", selected_proxy)
        else:
            return 'FAILED', (current_id, f"HTTP Hatası: {response.status_code}", selected_proxy)

    except requests.exceptions.RequestException as e:
        return 'FAILED', (current_id, f"Bağlantı/Proxy Hatası: {str(e)[:50]}", selected_proxy)
    except Exception as e:
        return 'FAILED', (current_id, f"Genel Hata: {str(e)[:50]}", selected_proxy)


# --- ANA ÇOKLU İŞLEME FONKSİYONU ---

def run_mass_text_export_parallel():
    
    start_id, count = get_user_inputs()
    proxies_list = load_proxies(PROXY_FILE)
    
    if not proxies_list:
        print("⚠️ Uyarı: Proxy listesi boş. İşlem tek IP üzerinden devam edecektir.")
        
    end_id = start_id + count - 1
    
    # Çıktı dosyalarını temizle
    if os.path.exists(OUTPUT_TXT_FILE): os.remove(OUTPUT_TXT_FILE)
    if os.path.exists(FAILED_ID_FILE): os.remove(FAILED_ID_FILE)
    
    print(f"\nID taraması {start_id}'den {end_id}'e kadar ({count} adet) {MAX_WORKERS} eş zamanlı iş parçacığı ile başlayacaktır.")
    print("-" * 50)
    
    successful_exports = 0
    id_range = range(start_id, end_id + 1)
    
    # ThreadPoolExecutor kullanarak paralel çalıştırma
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        
        # Tüm ID'ler için görevleri gönder
        future_to_id = {executor.submit(process_id, id_val, proxies_list): id_val for id_val in id_range}
        
        # tqdm ile ilerleme çubuğunu göster
        results_iterator = tqdm(as_completed(future_to_id), total=count, desc="Paralel Tarama İlerlemesi", unit="ID")

        for future in results_iterator:
            result_type, result_data = future.result()
            
            if result_type == 'SUCCESS':
                # Başarılı sonuçları ana dosyaya yazar
                with open(OUTPUT_TXT_FILE, 'a', encoding='utf-8') as f:
                    f.write(result_data)
                successful_exports += 1
                
            elif result_type == 'FAILED':
                # Başarısız sonuçları log dosyasına yazar
                current_id, reason, selected_proxy = result_data
                log_failed_id(current_id, reason, selected_proxy)
                
            # İlerleme çubuğunun açıklamasını güncelle
            results_iterator.set_postfix(Başarılı=successful_exports, Hata=results_iterator.n - successful_exports)


    print("-" * 50)
    print(f"İşlem tamamlandı. Toplam başarılı kayıt: {successful_exports}")
    print(f"Başarısız ID'ler {FAILED_ID_FILE} dosyasına kaydedildi.")

if __name__ == "__main__":
    run_mass_text_export_parallel()