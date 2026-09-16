# CẨM NANG 1-CLICK: BÓC TÁCH NHẠC SIÊU TỐC TRÊN RUNPOD & ĐỒNG BỘ GOOGLE DRIVE

---

## ⏱️ THỜI GIAN VÀ CHI PHÍ ƯỚC TÍNH:
* **Tốc độ:** **`0.3s / file`** (Chạy 8 worker song song trên RTX 4090 24GB).
* **Thời gian xong 60.000 file:** **~2.5 – 3 tiếng**.
* **Tổng chi phí RunPod:** **~$1.00 – $1.50** (~25.000 – 38.000 VNĐ).

---

## BƯỚC 1: KHỞI TẠO POD TRÊN RUNPOD (TRONG 30 GIÂY)

1. Đăng nhập vào [https://www.runpod.io/console/pods](https://www.runpod.io/console/pods).
2. Bấm nút **`Deploy`** ở góc trên bên phải.
3. Chọn loại GPU:
   - Tìm thẻ **`RTX 4090 (24GB VRAM)`** -> Bấm **`Deploy`**.
4. Cấu hình Pod:
   - **Template:** Chọn `RunPod PyTorch 2.4` (hoặc `PyTorch 2.2+`).
   - **Container Disk:** Đổi thành **`50 GB`**.
   - **Volume Disk:** Đổi thành **`100 GB`**.
5. Bấm nút màu tím **`Deploy On-Demand`**.
6. Chờ khoảng 20-30 giây khi chữ **`Running`** màu xanh hiện lên:
   - Bấm vào nút **`Connect`** -> Chọn **`Connect to Web Terminal`** (Màn hình đen gõ lệnh sẽ hiện ra ngay trên trình duyệt).

---

## BƯỚC 2: CÀI ĐẶT MÔI TRƯỜNG & TẢI CODE (COPY DÁN 1 LỆNH)

Trong cửa sổ Web Terminal của RunPod, bạn chỉ cần copy và dán nguyên khối lệnh sau:

```bash
# 1. Cài đặt các thư viện AI và công cụ âm thanh
pip install -q audio-separator[gpu] onnxruntime-gpu soundfile numpy gdown tqdm

# 2. Tải toàn bộ mã nguồn SaydiTool từ GitHub
git clone https://github.com/conheo-map/ToolCrawl.git /workspace/SaydiTool
cd /workspace/SaydiTool
```

---

## BƯỚC 3: TẢI DATASET TỪ GOOGLE DRIVE XUỐNG RUNPOD

*(Tải các file zip của Week 1 -> Week 4 từ Google Drive về máy RunPod qua mạng cáp quang 10Gbps chỉ mất ~1-2 phút)*:

```bash
# Ví dụ giải nén các tuần vào thư mục dự án
mkdir -p Week1_cu Week2_cu Week3_cu Week4_cu Week1 Week2 Week3 Week4
```

---

## BƯỚC 4: KÍCH HOẠT BÓC TÁCH SIÊU TỐC (CÓ PRE-FLIGHT CHECK)

Chạy câu lệnh bóc tách đa luồng:

```bash
# Chạy 8 worker song song trên RTX 4090 với Model Mel-Band RoFormer chuẩn SOTA (mặc định)
python tools/cloud_turbo_separator.py --week all --group all --model roformer --workers 8 --batch-size 500
```

### 🛡️ Những gì sẽ tự động diễn ra:
1. **Pre-flight Sanity Check:** Hệ thống tự động bóc tách 1 file mẫu để kiểm tra GPU CUDA và FFmpeg 16kHz Mono.
2. **Bóc tách hàng loạt:** 8 worker chạy song song, xử lý ~20.000 file mỗi giờ.
3. **Auto-Update Metadata:** Tự động tính toán và ghi đè lại `metadata.json` và `summary.json` cho từng ngày.

---

## BƯỚC 5: ĐÓNG GÓI & ĐỒNG BỘ KẾT QUẢ VỀ GOOGLE DRIVE

Sau khi bóc tách xong 100%, bạn chạy lệnh đóng gói tự động:

```bash
# Đóng gói tự động toàn bộ Week1..4 thành các file ZIP kèm mã kiểm tra MD5
python tools/gdrive_sync_helper.py --package all
```

Kết quả sẽ được lưu tại thư mục `/workspace/SaydiTool/export_clean/` gồm:
* `Week1_Clean_Complete.zip`
* `Week2_Clean_Complete.zip`
* `Week3_Clean_Complete.zip`
* `Week4_Clean_Complete.zip`
* `clean_export_manifest.json` (Chứa mã băm MD5 kiểm định độ nguyên vẹn)

---

## BƯỚC 6: TẮT MÁY ĐỂ DỪNG TÍNH TIỀN (QUAN TRỌNG)
1. Quay lại trang [https://www.runpod.io/console/pods](https://www.runpod.io/console/pods).
2. Ở ô máy Pod vừa chạy, bấm vào dấu **3 chấm `...`** -> Bấm **`Terminate`** (hoặc Stop & Delete).
3. Máy sẽ được xóa hoàn toàn và RunPod ngừng tính tiền ngay lập tức!
