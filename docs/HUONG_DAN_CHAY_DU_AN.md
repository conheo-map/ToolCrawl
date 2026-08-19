# 🚀 CẨM NANG TOÀN TẬP: 3 CÁCH CHẠY DỰ ÁN SAYDITOOL (LOCAL & CLOUD)

> **SaydiTool** cung cấp 3 phương thức vận hành linh hoạt phù hợp với từng hoàn cảnh sử dụng. Bạn có thể chọn cách phù hợp nhất bên dưới:

---

## 🧭 BẢNG SO SÁNH & LỰA CHỌN CÁCH CHẠY

| Phương thức | Khi nào nên dùng? | Yêu cầu máy tính | Thời gian xử lý | Chất lượng tách giọng AI |
|---|---|---|---|---|
| **CÁCH 1: Local CLI (`main.py`)** | Ngồi tại máy, muốn cào từ khóa, kênh, hoặc file `urls.txt` hàng loạt | 💻 Máy tính BẬT | ⚡ 5 - 10 giây / video | ★★★★★ Tối đa (3 tầng HPSS) |
| **CÁCH 2: Local Bot (`bot.py`)** | Đang ở nhà, lướt điện thoại thấy video hay bắn link về máy tính | 💻 Máy tính BẬT | ⚡ 5 - 10 giây / video | ★★★★★ Tối đa (3 tầng HPSS) |
| **CÁCH 3: Cloud GitHub Actions** | Đi ra ngoài, đi làm, đi ngủ, **TẮT máy tính hoàn toàn** | 📴 Máy tính TẮT 100% | ☁️ ~35 - 45 giây / video | ★★★★☆ Tốt (Cloud Fast Mode) |

---

## 💻 CÁCH 1: CHẠY LOCAL CLI (`python main.py`)
> **Mục đích:** Chạy trực tiếp từ dòng lệnh trên máy tính. Thích hợp nhất khi cào từ khóa tìm kiếm, quét toàn bộ kênh hoặc cào hàng loạt từ file `urls.txt`.

### 1. Chuẩn bị Terminal:
Mở **Windows PowerShell** tại thư mục dự án `C:\HocC\SaydiTool`:
```powershell
cd C:\HocC\SaydiTool
.\.venv\Scripts\Activate.ps1
```
*(Nếu hiện `(.venv) PS C:\HocC\SaydiTool>` là môi trường ảo đã kích hoạt thành công).*

---

### 2. Các câu lệnh chạy chi tiết:

#### 🔹 Trường hợp A: Cào danh sách link từ file `urls.txt` (Khuyên dùng)
Dán các link TikTok/Facebook vào file `urls.txt` (mỗi link 1 dòng), sau đó chạy:
```powershell
python main.py --platform tiktok --keyword "urls.txt" --workers 4
```
*Có sử dụng cookie:*
```powershell
python main.py --platform tiktok --keyword "urls.txt" --cookies cookies_tiktok.txt --workers 4
```

#### 🔹 Trường hợp B: Cào 1 link video TikTok / Facebook cụ thể
```powershell
# Link TikTok rút gọn hoặc link đầy đủ:
python main.py --platform tiktok --keyword "https://vt.tiktok.com/ZSM12345/"

# Link Facebook Reel / Video:
python main.py --platform facebook --keyword "https://www.facebook.com/reel/1410384157640503"
```

#### 🔹 Trường hợp C: Cào theo từ khóa tìm kiếm
```powershell
# Cào TikTok theo từ khóa:
python main.py --platform tiktok --keyword "review quán ăn Hà Nội" --max-results 100 --workers 4

# Cào Facebook theo từ khóa:
python main.py --platform facebook --keyword "học tiếng Việt giao tiếp" --max-results 100 --workers 4
```

#### 🔹 Trường hợp D: Cào toàn bộ video từ một kênh TikTok
```powershell
python main.py --platform tiktok --keyword "https://www.tiktok.com/@vtv24news" --max-results 200 --workers 4
```

#### 🔹 Trường hợp E: Chạy thử nghiệm xem link, không tải file (Dry Run)
```powershell
python main.py --platform tiktok --keyword "tin tức thời sự" --dry-run
```

#### 🔹 Trường hợp F: Tự động chạy lại các link bị lỗi trước đó
```powershell
python retry_failed.py
```

---

## 🤖 CÁCH 2: CHẠY LOCAL BOT TELEGRAM (`python bot.py`)
> **Mục đích:** Biến máy tính ở nhà thành trạm tiếp nhận dữ liệu. Bạn vừa lướt TikTok/FB trên điện thoại, thấy video hay chỉ cần bấm **Chia sẻ ➔ Copy link** gửi vào Telegram, máy tính sẽ tự động tải, tách nhạc AI 3 tầng và báo cáo về điện thoại.

### 1. Khởi động Bot trên máy tính:
Mở PowerShell tại `C:\HocC\SaydiTool` và chạy:
```powershell
cd C:\HocC\SaydiTool
.\.venv\Scripts\Activate.ps1

# Chạy bot với Token của bạn:
python bot.py --token "YOUR_TELEGRAM_BOT_TOKEN"
```

*Hoặc lưu token vào biến môi trường để không phải gõ lại:*
```powershell
$env:TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
python bot.py
```

Khi màn hình hiện:
```text
============================================================
🤖 TELEGRAM BOT SẴN SÀNG NHẬN LINK!
Gửi link TikTok/Facebook từ điện thoại vào Telegram Bot để cào tự động.
============================================================
```
👉 **Bot đã sẵn sàng 100%!** Bạn có thể thu nhỏ cửa sổ PowerShell để bot chạy ngầm.

---

### 2. Thao tác trên điện thoại:
1. Mở ứng dụng **Telegram** trên điện thoại ➔ Vào cuộc trò chuyện với Bot của bạn.
2. Gõ lệnh `/start` để xem hướng dẫn.
3. **Gửi link:**
   - **Gửi 1 link:** Dán link video TikTok / Facebook trực tiếp vào khung chat.
   - **Gửi nhiều link cùng lúc:** Dán danh sách link (mỗi link 1 dòng) vào 1 tin nhắn duy nhất:
     ```text
     https://vt.tiktok.com/ZSM12345/
     https://vt.tiktok.com/ZSM67890/
     https://www.facebook.com/reel/123456789
     ```
4. **Xem thống kê:** Gõ `/stats` để xem tổng số video và số giờ âm thanh đã cào trong ngày.

---

## ☁️ CÁCH 3: CHẠY 100% CLOUD (GITHUB ACTIONS + GOOGLE DRIVE)
> **Mục đích:** **TẮT MÁY TÍNH HOÀN TOÀN 100%**. Không tốn điện, không tốn dung lượng ổ cứng, không tốn băng thông mạng nhà. Cào trên máy chủ GitHub và tự động đẩy file vào Google Drive `Trương Duy Cường/Week2/`.

---

### 🔹 Cách 3A: Gửi link qua Telegram (Tự động kích hoạt Cloud)
1. Cầm điện thoại mở **Telegram** ➔ Gửi link hoặc danh sách link vào Bot.
2. **Cloudflare Worker** sẽ tự động kích hoạt **GitHub Actions**.
3. Máy chủ GitHub chạy ngầm:
   - Tải video.
   - Convert sang WAV chuẩn 16kHz mono.
   - Tách nhạc nền bằng **Cloud Fast Mode** (~1s/file).
   - Tự động dùng Rclone đẩy file sang Google Drive.
4. Bot Telegram gửi tin nhắn thông báo hoàn tất về điện thoại của bạn:
   ```text
   🎉 ĐÃ CÀO XONG VÀ ĐỒNG BỘ GOOGLE DRIVE!
   • 🎯 File thành công: 1 file
   • ⏱️ Tổng thời lượng: 0.03 giờ
   • ☁️ Thư mục Drive: Trương Duy Cường/Week2/
   ```

---

### 🔹 Cách 3B: Bấm nút chạy thủ công trên giao diện Web GitHub
Thích hợp khi bạn muốn cào một từ khóa mới hoặc chạy file `urls.txt` trên Cloud:

1. Mở trình duyệt web ➔ Truy cập: [github.com/conheo-map/ToolCrawl/actions](https://github.com/conheo-map/ToolCrawl/actions)
2. Ở danh sách bên trái, bấm chọn: **`Cloud Audio Crawler to Google Drive`**.
3. Bấm vào nút **`Run workflow`** ở góc bên phải:
   - **Nền tảng:** Chọn `tiktok` hoặc `facebook`.
   - **Keyword:** Nhập từ khóa tìm kiếm (VD: `ẩm thực đường phố`), link video, link kênh hoặc `urls.txt`.
   - **Workers:** Nhập số luồng (mặc định `4`).
4. Bấm nút màu xanh **`Run workflow`** ➔ Máy chủ Cloud sẽ tự động chạy và đẩy kết quả lên Google Drive.

---

### 🔹 Cách 3C: Tự động chạy theo lịch hẹn giờ 24/7 (Cron Schedule)
Hệ thống Cloud đã được cấu hình tự động kích hoạt **mỗi 4 tiếng 1 lần** (0h, 4h, 8h, 12h, 16h, 20h) để thu thập dữ liệu mới liên tục mà bạn không cần phải làm bất cứ thao tác nào.

---

## 📊 TỔNG HỢP CÁC LỆNH NHANH (CHEATSHEET)

```powershell
# 1. Kích hoạt môi trường ảo:
cd C:\HocC\SaydiTool
.\.venv\Scripts\Activate.ps1

# 2. Chạy Local CLI:
python main.py --platform tiktok --keyword "urls.txt" --workers 4

# 3. Chạy Local Telegram Bot:
python bot.py --token "YOUR_TELEGRAM_BOT_TOKEN"

# 4. Chạy toàn bộ 11 Unit Tests kiểm tra hệ thống:
pytest -o pythonpath=. -v

# 5. Đồng bộ thủ công Google Drive bằng Rclone từ máy tính:
rclone copy Week2/ gdrive,root_folder_id=16iuu3_UtaGtNEuHJksZAlEeBcqYhclSw:Week2/ --progress

# 6. Đẩy cập nhật code mới lên GitHub:
git add .
git commit -m "update: crawler settings"
git push origin main
```
