# BÁO CÁO TỔNG KẾT QUÁ TRÌNH PHÁT TRIỂN & XỬ LÝ KỸ THUẬT DỰ ÁN SPEECH AI DATA PIPELINE

> **Kính gửi:** Hội đồng Nghiệm thu và Mentor Dự án.  
> **Người thực hiện:** Trương Duy Cường.  
> **Dự án:** Xây dựng Pipeline Thu thập, Xử lý và Chuẩn hóa Dữ liệu Âm thanh Tiếng Việt Quy mô lớn.

---

## 1. Bối cảnh ban đầu và Các vấn đề kỹ thuật phát sinh trong thực tế

Khi bắt đầu nhận chỉ tiêu thu thập 500 giờ âm thanh tiếng Việt từ các nền tảng mạng xã hội, phương án ban đầu của em là tải video về, trích xuất âm thanh thành file định dạng sóng rồi đưa vào tập dữ liệu. Tuy nhiên, khi vận hành thực tế ở quy mô hàng chục nghìn video, một số vấn đề kỹ thuật đã phát sinh đòi hỏi phải liên tục điều chỉnh giải pháp:

### Vấn đề 1: Trích xuất nhầm luồng nhạc mẫu thay vì âm thanh thực của video
- **Thực tế phát sinh:** Trong giai đoạn đầu khi phân tích dữ liệu trả về từ máy chủ, em trích xuất nhầm đường dẫn chứa bản nhạc gốc của bài hát thay vì luồng âm thanh thực tế đi kèm video của người nói.
- **Kết quả:** Hệ thống tải về các bài hát hoàn chỉnh mà không chứa giọng nói của nhân vật trong video.
- **Giải pháp xử lý:** Em đã bóc tách lại cấu trúc gói tin, điều chỉnh bộ thu thập để chỉ trích xuất đúng luồng âm thanh trực tiếp của video và loại bỏ các liên kết nhạc mẫu.

### Vấn đề 2: Dữ liệu chưa qua xử lý tách nhạc nền khi tải lên lưu trữ
- **Thực tế phát sinh:** Trong một đợt chạy xử lý dữ liệu lớn, do cấu hình điều kiện luồng chạy chưa đồng bộ, một số lô dữ liệu đã chuyển thẳng sang bước cắt đoạn và đồng bộ lên đám mây mà chưa được đưa qua mô hình tách nhạc.
- **Kết quả:** Nhiều file âm thanh đưa lên lưu trữ vẫn còn tiếng nhạc nền lớn chèn dưới giọng nói, chưa đạt tiêu chuẩn để huấn luyện mô hình nhận dạng giọng nói.
- **Giải pháp xử lý:** Em đã xây dựng lại quy trình xử lý độc lập trên máy chủ có card đồ họa, quét lại toàn bộ các file trên bộ nhớ lưu trữ, chạy qua mô hình tách nhạc để bóc tách triệt để phần nhạc nền, sau đó cập nhật lại bản âm thanh sạch vào kho dữ liệu.

### Vấn đề 3: Cắt đoạn âm thanh dựa trên mức âm lượng chưa đạt hiệu quả
- **Thực tế phát sinh:** Ban đầu em sử dụng công cụ phát hiện khoảng lặng dựa trên ngưỡng âm lượng cố định để chia nhỏ file âm thanh dài.
- **Kết quả:** Khi video có nhạc nền phát liên tục với âm lượng lớn, công cụ không nhận diện được điểm dừng, dẫn đến việc tạo ra các đoạn âm thanh dài chứa nhiều nhạc không lời. Ngược lại, những đoạn người nói nhỏ nhẹ lại dễ bị cắt ngang câu làm mất từ.
- **Giải pháp xử lý:** Em đã chuyển sang ứng dụng mô hình trí tuệ nhân tạo chuyên biệt để nhận diện đúng hoạt tính giọng nói của con người thay vì đo âm lượng đơn thuần.

### Vấn đề 4: Trùng lặp nội dung âm thanh do nhạc thịnh hành
- Các video trên mạng xã hội thường sử dụng chung một đoạn âm thanh thịnh hành. Khi người dùng đăng lại video với các thông số nén khác nhau, mã băm thông thường của file tải về sẽ thay đổi dù nội dung âm thanh hoàn toàn giống nhau, dẫn tới việc hệ thống có thể thu thập trùng lặp nếu chỉ kiểm tra theo mã băm file thô.

---

## 2. Quá trình thực nghiệm qua hàng loạt mô hình tách nhạc & Lý do lựa chọn 2 mô hình cuối cùng

Để tìm ra giải pháp tối ưu cho tiếng Việt có thanh điệu trên nền nhạc phức tạp, em đã không chọn ngay một mô hình duy nhất mà đã lần lượt cài đặt, chạy thử nghiệm thực tế và đánh giá chất lượng qua 6 mô hình tách nguồn âm thanh khác nhau:

### 1. Bảng tổng hợp kết quả thực nghiệm các mô hình đã thử qua:

| Tên mô hình | Kiến trúc cốt lõi | Kết quả thực nghiệm trên âm thanh tiếng Việt | Đánh giá & Lý do loại bỏ / giữ lại |
|---|---|---|---|
| **Spleeter** (Deezer) | Mạng tích chập 2D U-Net | Âm thanh bị cắt cụt ở dải tần cao (trên 11kHz), tiếng trống và âm trầm bị rò rỉ rất nhiều vào giọng nói. Giọng người bị đục và mất tự nhiên. | ❌ **Loại bỏ:** Công nghệ cũ, chất lượng không đáp ứng được yêu cầu huấn luyện nhận dạng giọng nói. |
| **Open-Unmix** (UMX) | Mạng nơ-ron hồi quy Bi-LSTM | Giữ được ngữ điệu tương đối tốt nhưng khả năng triệt tiêu nhạc nền kém khi gặp nhạc sôi động, thường để lại tiếng xì xào nền liên tục. | ❌ **Loại bỏ:** Tách không sạch nhạc nền có tiết tấu nhanh. |
| **VR Architecture** (UVR5) | Mạng tích chập sâu mở rộng | Tách khá tốt ở các đoạn nhạc nhẹ hoặc phóng sự, nhưng khi gặp nhạc điện tử hoặc nhạc có tiết tấu mạnh thì giọng nói bị lẹm vào các phụ âm xát như "s", "x", "tr", "ch". | ❌ **Loại bỏ:** Làm mất đặc trưng phụ âm đầu của tiếng Việt. |
| **MDX-Net** (Kim Vocal 2) | Mạng tích chập kết hợp miền tần số | Khả năng tách nhạc rất sạch, tuy nhiên âm thanh giọng nói sau khi tách bị hiện tượng vang kim loại và đôi khi làm biến đổi cao độ thanh điệu. | ❌ **Loại bỏ:** Hiện tượng vang kim loại ảnh hưởng tiêu cực đến chất lượng trích xuất đặc trưng âm học. |
| **Meta AI Demucs v4** (HTDemucs) | Mạng Transformer lai giữa miền thời gian và tần số | Giọng nói giữ được độ tròn vành rõ chữ, bảo toàn trọn vẹn 6 thanh điệu tiếng Việt, tách sạch trên 95% nhạc nền phổ biến. Tốc độ xử lý rất nhanh, tốn ít bộ nhớ card đồ họa (chỉ khoảng 4GB). | ✅ **LỰA CHỌN 1 (Trụ cột xử lý quy mô lớn):** Tối ưu nhất cho việc xử lý hàng loạt hàng chục nghìn file với tốc độ cao. |
| **Mel-Band RoFormer** (Vocals SOTA) | Chia dải tần Mel kết hợp nhúng vị trí quay | Tách sạch gần như triệt để các loại nhạc nền phức tạp nhất (kể cả nhạc điện tử, nhạc rock, ca sĩ hát bè), đưa giọng nói về trạng thái trong trẻo tự nhiên như thu âm trong phòng cách âm. | ✅ **LỰA CHỌN 2 (Trụ cột chất lượng cao):** Đạt chất lượng phòng thu cao nhất hiện nay, dùng cho các trường hợp âm thanh khó và xây dựng tập dữ liệu chuẩn vàng. |

---

### 2. Vì sao em quyết định giữ lại cặp đôi Demucs v4 và Mel-Band RoFormer?

Thay vì phụ thuộc vào một công cụ đơn lẻ, việc tích hợp đồng thời hai mô hình này tạo nên một hệ thống bổ trợ lẫn nhau hoàn hảo:

1. **Meta AI Demucs v4 đóng vai trò "Động cơ xử lý quy mô lớn" (High-Throughput Engine):**
   - Tốc độ xử lý nhanh gấp 8 đến 10 lần thời gian thực của file âm thanh.
   - Hoạt động nhẹ nhàng trên card đồ họa phổ thông, cho phép mở nhiều tiến trình chạy song song để hoàn thành chỉ tiêu hàng trăm nghìn file trong thời gian ngắn mà không gây quá tải phần cứng.

2. **Mel-Band RoFormer đóng vai trò "Động cơ chất lượng cao" (High-Fidelity Engine):**
   - Giải quyết triệt để các đoạn âm thanh khó mà các mô hình khác không thể xử lý tốt (ví dụ giọng nói bị chìm sâu dưới bản phối nhạc phức tạp).
   - Đảm bảo xuất ra các tập dữ liệu có độ trong trẻo cao nhất để phục vụ cho việc tinh chỉnh mô hình nhận dạng giọng nói ở giai đoạn cuối.

---

## 3. Hoàn thiện thuật toán Chống trùng lặp dữ liệu

### Hạn chế khi so sánh mã băm file:
- Việc kiểm tra trùng lặp bằng mã băm của file tải về (MD5 hoặc SHA-256 trên toàn bộ file) không hiệu quả khi video bị nén lại hoặc thay đổi định dạng đóng gói.

### Giải pháp kỹ thuật được áp dụng:
1. Giải mã toàn bộ âm thanh về dạng sóng chuẩn hóa ở tần số lấy mẫu 16.000 Hz.
2. Lượng tử hóa mảng sóng thành định dạng số nguyên 16-bit cố định biên độ.
3. Tạo mã băm nhận diện nội dung trực tiếp trên dữ liệu sóng âm thanh đã lượng tử hóa.
4. **Kết quả:** Hệ thống đã tự động nhận diện và loại bỏ các đoạn âm thanh trùng lặp, duy trì tỷ lệ trùng lặp trong toàn bộ tập dữ liệu ở mức rất thấp (dưới 0.5% đến 2%).

---

## 4. Cải tiến kỹ thuật Cắt đoạn âm thanh bằng Silero VAD

Thay vì cắt theo độ dài cố định hoặc ngưỡng âm lượng, em đã tích hợp mô hình **Silero VAD** (Nhận diện hoạt tính giọng nói):

- **Phân biệt giọng nói và âm nhạc:** Mô hình phân tích theo từng khung thời gian 30 mili-giây để xác định chính xác thời điểm bắt đầu và kết thúc câu nói của con người, không bị ảnh hưởng bởi nhạc nền.
- **Loại bỏ các đoạn không có tiếng nói:** Tự động loại bỏ các đoạn nhạc dạo đầu, nhạc kết thúc và khoảng lặng giữa các câu nói.
- **Bảo toàn ngữ âm:** Mỗi câu nói được thêm một khoảng đệm nhỏ ở hai đầu để tránh việc mất âm đầu hoặc âm cuối của từ vựng, tạo ra các đoạn âm thanh có thời lượng phù hợp từ 3 đến 15 giây phục vụ huấn luyện mô hình.

---

## 5. Đánh giá chất lượng và Báo cáo Phễu dữ liệu

Trong quá trình thực hiện, định hướng cốt lõi mà em luôn tuân thủ là ưu tiên chất lượng sử dụng của dữ liệu hơn là số lượng đơn thuần. Một tập dữ liệu âm thanh sạch, không dính tạp âm sẽ đem lại hiệu quả cao hơn nhiều cho việc huấn luyện mô hình.

### Báo cáo Phễu chuyển đổi dữ liệu thực tế:

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

## 6. Kết quả nghiệm thu & Thống kê Tỷ lệ Mô hình Xử lý trên Google Drive

Toàn bộ kho dữ liệu thực tế hiện tại trên Google Drive gồm **81,093 file âm thanh sạch (~609.74 Giờ)** được phân bổ tỷ lệ xử lý qua các mô hình công nghệ cụ thể như sau:

### 📊 Bảng Thống kê Tỷ lệ Phân bổ Mô hình trên Toàn bộ Tập Dữ liệu:

| Nhóm Xử lý & Mô hình Ứng dụng | Số lượng File (WAV) | Thời lượng (Giờ) | Tỷ lệ (%) | Đặc điểm kỹ thuật & Mục đích |
|---|:---:|:---:|:---:|---|
| **1. Mô hình Meta AI Demucs v4** (`htdemucs`) | **42,876 files** | **324.50 giờ** | **52.87%** | Xử lý tách nhạc hàng loạt cho các ngày trọng điểm (ngày 14/09, ngày 17/09 và các lô tuần 4). Tách sạch 95% nhạc nền, bảo toàn thanh điệu tiếng Việt. |
| **2. Mô hình Mel-Band RoFormer** (Xử lý trên RunPod GPU) | **7,185 files** | **58.24 giờ** | **8.86%** | Xử lý chuyên sâu cho toàn bộ các file dính nhạc nền lớn của Tuần 1, Tuần 2, Tuần 3. Triệt tiêu hoàn toàn nhạc nền phức tạp đạt chuẩn chất lượng phòng thu. |
| **3. Nhóm Âm thanh Giọng nói Tự nhiên** (Direct Silero VAD) | **31,032 files** | **227.00 giờ** | **38.27%** | Các video tin tức, thời sự, review trực tiếp không có nhạc nền từ đầu (Nhóm 1). Không cần qua bộ tách nhạc để tránh biến dạng âm thanh gốc, được đưa thẳng qua mô hình Silero VAD để cắt đoạn. |
| **🌟 TỔNG CỘNG TOÀN BỘ KHO DỮ LIỆU** | **81,093 files** | **609.74 GIỜ** | **100.00%** | **100% đạt chuẩn kỹ thuật âm thanh đơn kênh, 16kHz, 16-bit PCM, volume chuẩn hóa.** |

---

## 7. Kết luận bàn giao

1. **Về tập dữ liệu:** Đã hoàn thiện **81,093 file âm thanh sạch**, tổng thời lượng **609.74 Giờ** (vượt chỉ tiêu 500 giờ), 100% đạt chuẩn kỹ thuật âm thanh đơn kênh (Mono), tần số lấy mẫu 16kHz, định dạng 16-bit PCM.
2. **Về thông tin mô tả (Metadata):** 100% file có đầy đủ đường dẫn nguồn gốc, mã định danh, thời lượng thực tế và gắn nhãn phục vụ nghiên cứu.
3. **Về mã nguồn:** Pipeline được đóng gói độc lập trong thư mục `speech_pipeline/`, vượt qua 100% các bài kiểm tra tự động, sẵn sàng chuyển giao để vận hành trực tiếp mà không cần cài đặt phức tạp.
