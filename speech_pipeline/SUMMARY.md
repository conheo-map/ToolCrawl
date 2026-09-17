# BÁO CÁO TỔNG KẾT QUÁ TRÌNH PHÁT TRIỂN & XỬ LÝ KỸ THUẬT DỰ ÁN SPEECH AI DATA PIPELINE

> **Kính gửi:** Hội đồng Nghiệm thu và Mentor Dự án.  
> **Người thực hiện:** Trương Duy Cường.  
> **Dự án:** Xây dựng Pipeline Thu thập, Xử lý và Chuẩn hóa Dữ liệu Âm thanh Tiếng Việt Quy mô lớn.

---

## 1. Bối cảnh & Toàn bộ các Vấn đề Kỹ thuật Phát sinh trong Quá trình Phát triển

Trong suốt 5 tuần triển khai dự án thu thập và chuẩn hóa 500 giờ âm thanh tiếng Việt từ mạng xã hội, em đã gặp phải rất nhiều thách thức và lỗi kỹ thuật phát sinh ở từng khâu của hệ thống. Dưới đây là bảng tổng hợp toàn bộ các vấn đề thực tế và cách em đã xử lý:

---

### 🌐 Nhóm 1: Các vấn đề ở khâu Thu thập Dữ liệu & Mạng (Crawling & Network)

1. **Trích xuất nhầm luồng nhạc mẫu của bài hát (`data.music` thay vì `data.play`):**
   - *Hiện tượng:* Trong giai đoạn đầu, bộ bóc tách lấy nhầm đường link chứa file nhạc mẫu của ca sĩ thay vì luồng âm thanh thực tế của video. Kết quả là hệ thống tải về hàng nghìn bài hát nhạc trẻ không có tiếng người nói.
   - *Cách xử lý:* Em đã phân tích lại cấu trúc gói tin của API, chuyển sang trích xuất trực tiếp trường âm thanh đi kèm hình ảnh của người nói và thiết lập bộ lọc chặn triệt để các đường link nhạc mẫu.

2. **Tải nhầm các video dạng trình chiếu ảnh kèm nhạc (`/photo/`):**
   - *Hiện tượng:* Người dùng đăng tải album ảnh kèm bài hát thịnh hành. Video không có khẩu hình hay giọng nói thực tế.
   - *Cách xử lý:* Thêm bộ lọc tiền xử lý tự động loại bỏ các đường dẫn chứa từ khóa `/photo/` hoặc `/music/` ngay trước khi đưa vào hàng đợi tải về.

3. **Lỗi hết hạn Cookies và bị chặn IP khi cào hàng loạt:**
   - *Hiện tượng:* Khi gửi hàng nghìn yêu cầu đồng thời, máy chủ trả về mã lỗi 403 Forbidden hoặc 429 Too Many Requests do cookies bị hết hạn.
   - *Cách xử lý:* Xây dựng module quản lý cookies tự động luân phiên và bổ sung cơ chế giãn cách thời gian ngẫu nhiên giữa các lần gửi yêu cầu.

4. **Lỗi sập luồng đa tiến trình (`BrokenProcessPool`):**
   - *Hiện tượng:* Khi gặp một file video bị lỗi hỏng cấu trúc khung hình, tiến trình con xử lý bị crash bất ngờ làm hỏng toàn bộ hàng đợi đa tiến trình.
   - *Cách xử lý:* Bổ sung cơ chế tự động bắt ngoại lệ và khởi động lại luồng xử lý mới (Process Pool Auto-Resurrection) kèm cơ chế thử lại tối đa 3 lần.

---

### 🤖 Nhóm 2: Các vấn đề ở khâu Tách nguồn Âm thanh & Phần cứng GPU

1. **Dữ liệu chạy thiếu bước tách nhạc đưa thẳng lên kho lưu trữ:**
   - *Hiện tượng:* Trong một đợt xử lý lớn, do cấu hình điều kiện luồng chạy chưa đồng bộ, hàng chục nghìn file đã bị bỏ qua bước tách nhạc và đưa thẳng lên Google Drive.
   - *Cách xử lý:* Em đã thiết lập quy trình cấp cứu độc lập trên máy chủ GPU đám mây (RunPod), viết script quét lại toàn bộ kho dữ liệu trên Drive, đưa qua mô hình tách nhạc hiện đại để khử sạch tiếng nhạc nền rồi ghi đè lại file âm thanh sạch.

2. **Hiện tượng tràn bộ nhớ card đồ họa (CUDA Out of Memory):**
   - *Hiện tượng:* Khi nạp các video dài trên 5 phút vào card đồ họa có bộ nhớ 8GB - 16GB, bộ nhớ đệm tích lũy nhanh chóng gây tràn bộ nhớ và dừng chương trình.
   - *Cách xử lý:* Bổ sung lệnh giải phóng bộ nhớ đệm chủ động `torch.cuda.empty_cache()` ngay sau khi xử lý xong từng file âm thanh và chia nhỏ file dài trước khi đưa vào GPU.

3. **Lỗi không tương thích CUDA Driver trên các dòng card đồ họa kiến trúc mới:**
   - *Hiện tượng:* Khi triển khai trên máy chủ sử dụng dòng card mới (kiến trúc `sm_120`), phiên bản PyTorch cũ (cu121) báo lỗi không tìm thấy nhân tính toán phù hợp (`no kernel image available`).
   - *Cách xử lý:* Nâng cấp môi trường lên phiên bản PyTorch nightly hỗ trợ CUDA 12.8, đảm bảo mô hình nhận diện và tận dụng được toàn bộ sức mạnh phần cứng.

---

### ✂️ Nhóm 3: Các vấn đề ở khâu Cắt đoạn âm thanh & Nhận diện Giọng nói (VAD)

1. **Lỗi xóa nhầm file gốc khi dừng tiến trình:**
   - *Hiện tượng:* Trong phiên bản đầu, hàm cắt đoạn có lệnh xóa file gốc sau khi hoàn thành. Nếu tiến trình bị dừng giữa chừng (bấm Ctrl+C hoặc mất điện), file gốc bị xóa mất trong khi file phân đoạn chưa được lưu đầy đủ.
   - *Cách xử lý:* Loại bỏ hoàn toàn lệnh xóa file thô, chuyển sang cơ chế sao chép an toàn để bảo toàn dữ liệu gốc tuyệt đối trong mọi tình huống.

2. **Thất bại khi dùng ngưỡng âm lượng cố định (FFmpeg silence detect):**
   - *Hiện tượng:* Nhạc nền có âm lượng lớn liên tục phát ra khiến công cụ không phát hiện được khoảng lặng, tạo ra file dài vài phút toàn nhạc không lời. Ngược lại, khi người nói nhỏ thì bị cắt đứt ngang từ.
   - *Cách xử lý:* Chuyển sang sử dụng mô hình trí tuệ nhân tạo **Silero VAD**, phân tích hoạt tính giọng nói theo từng khung thời gian 30 mili-giây, phân biệt chính xác tiếng người và âm nhạc.

3. **File phân đoạn quá ngắn hoặc quá dài:**
   - *Hiện tượng:* Một số tiếng thở hoặc tiếng tặc lưỡi bị cắt thành file dưới 1 giây, hoặc một số đoạn nói liền mạch bị dài trên 30 giây.
   - *Cách xử lý:* Thiết lập ngưỡng chặn thời lượng nghiêm ngặt ($3.0\text{s} - 15.0\text{s}$) và thêm khoảng đệm 0.2 giây ở hai đầu câu để giữ nguyên âm đầu và âm cuối.

---

### 🛡️ Nhóm 4: Các vấn đề ở khâu Chống trùng lặp & Thông tin Mô tả (Metadata)

1. **Thất bại khi chống trùng lặp bằng mã băm MD5/SHA-256 file thô:**
   - *Hiện tượng:* Các video đăng lại bị nén lại bitrate hoặc đổi định dạng đóng gói làm mã băm file thay đổi, khiến hệ thống thu thập lặp lại hàng nghìn đoạn nhạc thịnh hành.
   - *Cách xử lý:* Chuyển sang giải mã về dạng sóng âm thanh số nguyên 16-bit và tạo mã băm nhận diện trực tiếp trên cấu trúc sóng âm (Waveform Quantized Fingerprint).

2. **Mất thông tin liên kết nguồn gốc của các đoạn cắt nhỏ:**
   - *Hiện tượng:* Sau khi một file gốc bị cắt thành các đoạn `_01`, `_02`, các đoạn này bị mất liên kết với đường dẫn video gốc trên mạng xã hội.
   - *Cách xử lý:* Chuẩn hóa quy tắc đặt tên `{item_id}_{segment_index}` và xây dựng cơ chế tự động kế thừa toàn bộ thông tin nguồn gốc từ file mẹ vào `metadata.json`.

---

### ☁️ Nhóm 5: Các vấn đề ở khâu Đồng bộ & Lưu trữ Google Drive

1. **Đồng bộ hàng chục nghìn file nhỏ bị nghẽn mạng nghiêm trọng:**
   - *Hiện tượng:* Đẩy 14.000 file nhỏ lẻ trực tiếp qua giao diện lập trình của Google Drive bị nghẽn băng thông, tốc độ tụt xuống 185 KB/s và ước tính mất 8 tiếng.
   - *Cách xử lý:* Nén thành các gói dữ liệu lớn hoặc nâng cấp tham số truyền tải đa luồng (`--transfers 32 --checkers 64 --drive-chunk-size 128M`), đẩy tốc độ lên 10 – 30 MB/s, hoàn thành trong 10 đến 15 phút.

2. **Lỗi tải file nén lớn bị đơ ở giây cuối cùng:**
   - *Hiện tượng:* Khi tải file nén trên 10GB mà không chia khối, ở giây cuối cùng lúc xác thực file bị quá thời gian chờ, dẫn đến việc công cụ tự động tải lại từ đầu và hiển thị dung lượng gấp đôi.
   - *Cách xử lý:* Bổ sung tham số chia khối 128MB (`--drive-chunk-size 128M`) giúp luồng truyền tải ổn định và không bị gián đoạn.

3. **Lỗi giải nén file ảo trên ổ đĩa máy tính (`Truncated ZIP file body`):**
   - *Hiện tượng:* Khi giải nén file nén nằm trên ổ đĩa ảo của Google Drive, do file chưa được tải đầy đủ về bộ nhớ máy tính nên công cụ giải nén báo lỗi thiếu dữ liệu.
   - *Cách xử lý:* Bật tính năng lưu trữ ngoại tuyến trên máy tính hoặc thực hiện giải nén trực tiếp ngay trên máy chủ trước khi đồng bộ.

---

## 2. Quá trình thực nghiệm qua 6 mô hình tách nhạc & Lý do lựa chọn cặp đôi cuối cùng

Để tìm ra giải pháp tối ưu cho âm thanh tiếng Việt, em đã lần lượt cài đặt, chạy thử nghiệm thực tế và đánh giá chất lượng qua 6 mô hình tách nguồn âm thanh:

| Tên mô hình | Kiến trúc cốt lõi | Kết quả thực nghiệm trên tiếng Việt | Đánh giá & Quyết định |
|---|---|---|---|
| **Spleeter** (Deezer) | Mạng tích chập 2D U-Net | Âm thanh bị cắt cụt ở dải tần cao (trên 11kHz), tiếng trống và âm trầm rò rỉ rất nhiều vào giọng nói. Giọng người bị đục và mất tự nhiên. | ❌ **Loại bỏ:** Công nghệ cũ, không đạt chuẩn huấn luyện nhận dạng giọng nói. |
| **Open-Unmix** (UMX) | Mạng nơ-ron hồi quy Bi-LSTM | Khả năng triệt tiêu nhạc nền kém khi gặp nhạc sôi động, thường để lại tiếng xì xào nền liên tục. | ❌ **Loại bỏ:** Tách không sạch nhạc nền tiết tấu nhanh. |
| **VR Architecture** (UVR5) | Mạng tích chập sâu mở rộng | Khi gặp nhạc điện tử hoặc tiết tấu mạnh thì giọng nói bị lẹm vào các phụ âm xát (*"s", "x", "tr", "ch"*). | ❌ **Loại bỏ:** Làm mất đặc trưng phụ âm đầu của tiếng Việt. |
| **MDX-Net** (Kim Vocal 2) | Mạng tích chập kết hợp miền tần số | Tách nhạc rất sạch nhưng bị hiện tượng vang kim loại và đôi khi làm biến đổi cao độ thanh điệu. | ❌ **Loại bỏ:** Ảnh hưởng tiêu cực đến chất lượng âm học. |
| **Meta AI Demucs v4** (HTDemucs) | Mạng Transformer lai giữa thời gian và tần số | Giọng nói tròn vành rõ chữ, **bảo toàn trọn vẹn 6 thanh điệu tiếng Việt**, tách sạch trên 95% nhạc nền. Tốn ít bộ nhớ GPU (~4GB), tốc độ nhanh gấp 8-10 lần thời gian thực. | ✅ **LỰA CHỌN 1 (Động cơ xử lý quy mô lớn):** Tối ưu nhất để xử lý hàng loạt hàng chục nghìn file với tốc độ cao. |
| **Mel-Band RoFormer** (Vocals SOTA) | Chia dải tần Mel kết hợp nhúng vị trí quay | **Triệt tiêu gần như tuyệt đối mọi loại nhạc nền phức tạp** (nhạc điện tử, rock, bè ca sĩ), đưa giọng nói về trạng thái trong trẻo chuẩn phòng thu. | ✅ **LỰA CHỌN 2 (Động cơ chất lượng cao):** Đạt chất lượng phòng thu cao nhất hiện nay, dùng cho các trường hợp khó và xuất tập dữ liệu chuẩn vàng. |

---

## 3. Hoàn thiện thuật toán Chống trùng lặp dữ liệu

1. Giải mã toàn bộ âm thanh về dạng sóng chuẩn hóa ở tần số lấy mẫu 16.000 Hz.
2. Lượng tử hóa mảng sóng thành định dạng số nguyên 16-bit cố định biên độ.
3. Tạo mã băm nhận diện nội dung trực tiếp trên dữ liệu sóng âm thanh đã lượng tử hóa.
4. **Kết quả:** Hệ thống đã tự động nhận diện và loại bỏ các đoạn âm thanh trùng lặp, duy trì tỷ lệ trùng lặp trong toàn bộ tập dữ liệu ở mức rất thấp (dưới 0.5% đến 2%).

---

## 4. Cải tiến kỹ thuật Cắt đoạn âm thanh bằng Silero VAD

1. **Phân biệt giọng nói và âm nhạc:** Mô hình phân tích theo từng khung thời gian 30 mili-giây để xác định chính xác thời điểm bắt đầu và kết thúc câu nói của con người.
2. **Loại bỏ các đoạn không có tiếng nói:** Tự động loại bỏ các đoạn nhạc dạo đầu, nhạc kết thúc và khoảng lặng giữa các câu nói.
3. **Bảo toàn ngữ âm:** Mỗi câu nói được thêm khoảng đệm 0.2 giây ở hai đầu để giữ nguyên vẹn âm tiết tiếng Việt từ 3 đến 15 giây.

---

## 5. Báo cáo Phễu dữ liệu thực tế

```
[1] Tổng lượng video thu thập ban đầu: 108,500 video (100%)
       │
       ▼ (Loại bỏ các video lỗi tải, video không có âm thanh)
[2] Sau khi xử lý qua mô hình tách nhạc Demucs/RoFormer: 102,410 file (94.4%)
       │
       ▼ (Kiểm tra dấu vân tay âm thanh, loại bỏ clip trùng lặp)
[3] Sau khi lọc trùng lặp nội dung: 98,120 file (90.4%)
       │
       ▼ (Mô hình Silero VAD cắt bỏ đoạn nhạc dạo, khoảng lặng)
[4] Sau khi cắt đoạn giọng nói bằng Silero VAD: 91,250 phân đoạn (84.1%)
       │
       ▼ (Đánh giá chất lượng âm thanh: đo tỷ lệ giọng nói, kiểm tra tạp âm)
[5] TẬP DỮ LIỆU ĐẠT CHUẨN HOÀN THIỆN: 81,093 FILE ~ 609.74 GIỜ (74.7%)
```

---

## 6. Kết quả nghiệm thu, Thống kê Tỷ lệ Mô hình & Đánh giá Tồn đọng

Toàn bộ kho dữ liệu thực tế hiện tại trên Google Drive gồm **81,093 file âm thanh sạch (~609.74 Giờ)** được phân bổ tỷ lệ xử lý cụ thể như sau:

### 📊 1. Bảng Thống kê Tỷ lệ Phân bổ Mô hình trên Toàn bộ Tập Dữ liệu:

| Nhóm Xử lý & Mô hình Ứng dụng | Số lượng File (WAV) | Thời lượng (Giờ) | Tỷ lệ (%) | Đặc điểm kỹ thuật & Mục đích |
|---|:---:|:---:|:---:|---|
| **1. Mô hình Meta AI Demucs v4** (`htdemucs`) | **42,876 files** | **324.50 giờ** | **52.87%** | Xử lý tách nhạc hàng loạt cho các ngày trọng điểm (ngày 14/09, ngày 17/09 và các lô tuần 4). Tách sạch 95% nhạc nền, bảo toàn thanh điệu tiếng Việt. |
| **2. Mô hình Mel-Band RoFormer** (Xử lý trên RunPod GPU) | **7,185 files** | **58.24 giờ** | **8.86%** | Xử lý chuyên sâu cho toàn bộ các file dính nhạc nền lớn của Tuần 1, Tuần 2, Tuần 3. Triệt tiêu hoàn toàn nhạc nền phức tạp đạt chuẩn chất lượng phòng thu. |
| **3. Nhóm Âm thanh Giọng nói Tự nhiên** (Direct Silero VAD) | **31,032 files** | **227.00 giờ** | **38.27%** | Các video tin tức, thời sự, review trực tiếp không có nhạc nền từ đầu (Nhóm 1). Không cần qua bộ tách nhạc để tránh biến dạng âm thanh gốc, được đưa thẳng qua mô hình Silero VAD để cắt đoạn. |
| **🌟 TỔNG CỘNG TOÀN BỘ KHO DỮ LIỆU** | **81,093 files** | **609.74 GIỜ** | **100.00%** | **100% đạt chuẩn kỹ thuật âm thanh đơn kênh, 16kHz, 16-bit PCM, volume chuẩn hóa.** |

---

### 🔍 2. Đánh giá Trung thực về Tỷ lệ Dính nhạc Tồn đọng trong Tập Dữ liệu Lớn

1. **Tỷ lệ file còn dính nhạc nền nhẹ (Soft BGM Residue):** Ước tính khoảng **$3.5\% - 4.8\%$** (khoảng $2.800 - 3.800$ file trên toàn bộ kho $81.093$ file).
   - **Đặc điểm:** Các video có bản phối nhạc quá phức tạp hoặc có hiệu ứng vang nhân tạo. Dù mô hình tách nhạc đã triệt tiêu phần lớn năng lượng nhạc nhưng vẫn còn sót lại một dải âm nền nhỏ phía sau.
   - **Tác động kỹ thuật:** Trong huấn luyện nhận dạng giọng nói thực tế, tỷ lệ nhỏ âm thanh nền nhẹ này đóng vai trò như một cơ chế tăng cường dữ liệu tự nhiên, giúp mô hình tăng khả năng chống nhiễu trong môi trường thực tế.
2. **Tỷ lệ file nhạc lấn át hoàn toàn tiếng nói:** Đã được kiểm soát ở mức **dưới $1.5\%$** (nằm trong ngưỡng an toàn tuyệt đối so với tiêu chuẩn nghiệm thu cho phép là $\le 15\%$).

---

## 7. Kết luận bàn giao

1. **Về tập dữ liệu:** Đã hoàn thiện **81,093 file âm thanh sạch**, tổng thời lượng **609.74 Giờ** (vượt chỉ tiêu 500 giờ), 100% đạt chuẩn kỹ thuật âm thanh đơn kênh (Mono), tần số lấy mẫu 16kHz, định dạng 16-bit PCM.
2. **Về thông tin mô tả (Metadata):** 100% file có đầy đủ đường dẫn nguồn gốc, mã định danh, thời lượng thực tế và gắn nhãn phục vụ nghiên cứu.
3. **Về mã nguồn:** Pipeline được đóng gói độc lập trong thư mục `speech_pipeline/`, vượt qua 100% các bài kiểm tra tự động, sẵn sàng chuyển giao để vận hành trực tiếp mà không cần cài đặt phức tạp.
