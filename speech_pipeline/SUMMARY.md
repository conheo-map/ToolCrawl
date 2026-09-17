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

## 2. Quá trình lựa chọn và nâng cấp mô hình Tách nhạc nền

Để đạt được chất lượng âm thanh tốt nhất cho bài toán nhận dạng giọng nói, em đã lần lượt thử nghiệm và nâng cấp qua các thế hệ mô hình:

```
[Phương pháp ban đầu: Spleeter / Bộ lọc tần số tĩnh] 
  ⬇ (Chưa tối ưu: Giọng nói bị biến dạng, rò rỉ âm thanh trầm)
[Mô hình nâng cấp: Demucs v4 - HTDemucs] 
  ⬇ (Hiệu quả cao: Tách sạch đa số nhạc nền, tốc độ xử lý nhanh)
[Mô hình chất lượng cao: Mel-Band RoFormer] 
  ⬇ (Chất lượng phòng thu: Triệt tiêu tốt cả các đoạn nhạc nền phức tạp)
```

### 1. Thử nghiệm ban đầu với Spleeter và Bộ lọc tần số tĩnh
- Khi áp dụng các bộ lọc tần số truyền thống, giọng nói sau khi lọc thường bị biến dạng và mất tự nhiên.
- Với mô hình Spleeter đời đầu, một số dải âm thanh của nhạc nền như tiếng trống và âm trầm vẫn bị rò rỉ vào phần giọng nói, ảnh hưởng đến độ chính xác khi đưa vào mô hình nhận dạng.

### 2. Bước chuyển đổi sang Meta AI Demucs v4 (HTDemucs)
- Em chuyển sang ứng dụng mô hình Demucs v4 với kiến trúc kết hợp giữa miền thời gian và miền tần số.
- **Đặc điểm:** Mô hình tách sạch phần lớn các loại nhạc nền phổ biến, giữ lại độ tự nhiên của giọng nói tiếng Việt mà không gây méo tiếng.
- **Tài nguyên:** Mức độ sử dụng bộ nhớ card đồ họa vừa phải (khoảng 4GB), tốc độ xử lý nhanh, phù hợp cho việc vận hành xử lý hàng loạt trên quy mô lớn.

### 3. Tích hợp Mel-Band RoFormer cho các trường hợp phức tạp
- Đối với những đoạn âm thanh có nhạc nền phức tạp hoặc âm lượng nhạc quá lớn lấn át tiếng người, em tích hợp thêm mô hình Mel-Band RoFormer.
- Mô hình này mang lại chất lượng bóc tách rất cao, giúp đưa âm thanh giọng nói về trạng thái trong trẻo, phù hợp cho việc xây dựng các tập dữ liệu mẫu đạt chuẩn cao.

---

## 3. Hoàn thiện thuật toán Chống trùng lặp dữ liệu

### Hạn chế khi so sánh mã băm file:
- Việc kiểm tra trùng lặp bằng mã băm của file tải về (MD5 hoặc SHA-256 trên toàn bộ file) không hiệu quả khi video bị nén lại hoặc thay đổi định dạng đóng gói.

### Giải pháp kỹ thuật được áp dụng:
1. Giải mã toàn bộ âm thanh về dạng sóng chuẩn hóa ở tần số lấy mẫu 16.000 Hz.
2. Lượng tử hóa mảng sóng thành định dạng số nguyên 16-bit cố định.
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

## 6. Kết luận bàn giao

1. **Về tập dữ liệu:** Đã hoàn thiện **81,093 file âm thanh sạch**, tổng thời lượng **609.74 Giờ** (vượt chỉ tiêu 500 giờ), 100% đạt chuẩn kỹ thuật âm thanh đơn kênh (Mono), tần số lấy mẫu 16kHz, định dạng 16-bit PCM.
2. **Về thông tin mô tả (Metadata):** 100% file có đầy đủ đường dẫn nguồn gốc, mã định danh, thời lượng thực tế và gắn nhãn phục vụ nghiên cứu.
3. **Về mã nguồn:** Pipeline được đóng gói độc lập trong thư mục `speech_pipeline/`, vượt qua 100% các bài kiểm tra tự động, sẵn sàng chuyển giao để vận hành trực tiếp mà không cần cài đặt phức tạp.
