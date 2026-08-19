# 📱 HƯỚNG DẪN THIẾT LẬP: GỬI LINK TELEGRAM ➔ CÀO CLOUD GITHUB ACTIONS ➔ ĐẨY GOOGLE DRIVE
> **Mục tiêu:** Cầm điện thoại gửi link TikTok/Facebook vào Telegram. Máy chủ GitHub tự động cào, lọc nhạc AI, đẩy sang Google Drive và báo cáo lại Telegram mà **KHÔNG CẦN BẬT MÁY TÍNH Ở NHÀ**.

---

## 🔄 Luồng hoạt động:
```text
[Điện thoại của bạn] 
  ➔ Gửi link vào Telegram Bot
  ➔ Cloudflare Worker (Miễn phí) nhận tin nhắn
  ➔ Kích hoạt GitHub Actions chạy ngầm trên Cloud
  ➔ Tải video, convert 16kHz mono, chạy AI tách nhạc
  ➔ Rclone đẩy thẳng file .wav sang Google Drive
  ➔ Gửi tin nhắn về Telegram: "🎉 Đã hoàn tất và lưu vào Google Drive!"
```

---

## 🛠️ CÁC BƯỚC CẤU HÌNH (LÀM 1 LẦN DUY NHẤT TRONG 5 PHÚT):

### BƯỚC 1: Lấy Token Bot Telegram từ `@BotFather`
1. Mở app **Telegram** trên điện thoại -> Tìm kiếm: `@BotFather`.
2. Gõ lệnh: `/newbot` -> Nhập tên Bot (VD: `Saydi Cloud Crawler`).
3. Nhập username (VD: `saydi_asr_cloud_bot`).
4. Copy mã **HTTP API Token** (VD: `7123456789:ABCdefGhIJKlmNoPQRstuVWXyz`).

---

### BƯỚC 2: Tạo GitHub Personal Access Token (PAT)
1. Mở trình duyệt vào GitHub -> Bấm vào ảnh Avatar góc trên bên phải -> Chọn **Settings**.
2. Cuộn xuống dưới cùng bên trái -> Chọn **Developer settings** -> **Personal access tokens** -> **Tokens (classic)**.
3. Bấm **Generate new token (classic)**:
   - Note: `Saydi Telegram Trigger`
   - Expiration: `No expiration` (hoặc 90 days).
   - Tích chọn quyền: `repo` (Full control of private repositories) và `workflow`.
4. Bấm **Generate token** và copy đoạn mã token (VD: `ghp_xxxxxxxxxxxxxxxxxxxxxx`).

---

### BƯỚC 3: Cấu hình Secrets trên Repo GitHub
1. Vào trang Repo GitHub `SaydiTool` của bạn -> Bấm tab **Settings** -> **Secrets and variables** -> **Actions**.
2. Thêm 2 Secrets sau:
   - Secret 1: **`RCLONE_CONFIG`** (Dán nội dung file cấu hình Rclone `rclone.conf` của bạn).
   - Secret 2: **`TELEGRAM_BOT_TOKEN`** (Dán Token Bot Telegram lấy ở Bước 1).

---

### BƯỚC 4: Tạo Cloudflare Worker miễn phí làm cầu nối (2 phút)
1. Truy cập trang web miễn phí: [dash.cloudflare.com](https://dash.cloudflare.com) (Đăng ký tài khoản miễn phí nếu chưa có).
2. Vào mục **Workers & Pages** -> Bấm **Create application** -> **Create Worker**.
3. Đặt tên (VD: `saydi-telegram-bridge`) -> Bấm **Deploy**.
4. Bấm vào nút **Edit code** và dán toàn bộ đoạn code dưới đây vào:

```javascript
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Saydi Telegram Webhook is active!", { status: 200 });
    }

    try {
      const update = await request.json();
      const message = update.message;
      if (!message || !message.text) return new Response("OK");

      const chatId = message.chat.id;
      const text = message.text.trim();

      // Trích xuất URLs
      const urlRegex = /(https?:\/\/(?:www\.|vt\.|vm\.)?(?:tiktok\.com|facebook\.com|fb\.watch)\/[^\s]+)/gi;
      const urls = text.match(urlRegex);

      if (text === "/start" || text === "/help") {
        await sendMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          "👋 *Saydi Cloud Crawler Bot*\n\nChỉ cần gửi link TikTok hoặc Facebook vào đây. Máy chủ GitHub Actions sẽ tự động cào ngầm, lọc nhạc AI và đẩy thẳng vào Google Drive của bạn!"
        );
        return new Response("OK");
      }

      if (!urls || urls.length === 0) {
        await sendMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          "ℹ️ Vui lòng gửi link TikTok hoặc Facebook hợp lệ!"
        );
        return new Response("OK");
      }

      // Thông báo đã nhận lệnh
      await sendMessage(
        env.TELEGRAM_BOT_TOKEN,
        chatId,
        `⏳ *Đã nhận link!*\n\`${urls[0]}\`\n\n🚀 Đang kích hoạt máy chủ GitHub Actions cào trên Cloud & đẩy sang Google Drive...`
      );

      // Kích hoạt GitHub Actions qua API repository_dispatch
      const ghResponse = await fetch(
        `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
        {
          method: "POST",
          headers: {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": `Bearer ${env.GITHUB_PAT}`,
            "User-Agent": "Cloudflare-Telegram-Bridge",
          },
          body: JSON.stringify({
            event_type: "telegram_crawl",
            client_payload: {
              url: urls[0],
              chat_id: chatId.toString(),
            },
          }),
        }
      );

      if (!ghResponse.ok) {
        await sendMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          "❌ Lỗi kích hoạt GitHub Actions. Vui lòng kiểm tra lại GITHUB_PAT!"
        );
      }
    } catch (err) {
      console.error(err);
    }

    return new Response("OK");
  },
};

async function sendMessage(token, chatId, text) {
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: "Markdown",
    }),
  });
}
```

5. Bấm **Deploy** -> Quay ra trang Settings của Worker -> Chọn tab **Settings** -> **Variables and Secrets** -> Thêm 3 biến môi trường:
   - **`TELEGRAM_BOT_TOKEN`**: Token Bot Telegram của bạn ở Bước 1.
   - **`GITHUB_REPO`**: Đường dẫn repo dạng `username/SaydiTool` (VD: `cuongdev/SaydiTool`).
   - **`GITHUB_PAT`**: Token GitHub cá nhân lấy ở Bước 2.
6. Copy đường link URL của Worker vừa tạo (dạng: `https://saydi-telegram-bridge.<subdomain>.workers.dev`).

---

### BƯỚC 5: Đăng ký Webhook với Telegram (30 giây)
Mở trình duyệt bất kỳ (trên điện thoại hoặc máy tính), dán đường link sau vào thanh địa chỉ rồi nhấn Enter (Thay TOKEN và URL Worker của bạn vào):

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://saydi-telegram-bridge.<subdomain>.workers.dev
```

👉 Màn hình hiện: `{"ok":true,"result":true,"description":"Webhook was set"}` là **HOÀN TẤT 100%!**

---

## 📱 CÁCH SỬ DỤNG HÀNG NGÀY:
1. Bạn đang đi ngoài đường, ngồi cafe hoặc nằm giường lướt TikTok / Facebook trên điện thoại.
2. Thấy video hay -> Bấm **Chia sẻ ➔ Sao chép liên kết** -> Gửi vào Telegram Bot.
3. Bot lập tức phản hồi: *"⏳ Đã nhận link! Đang kích hoạt GitHub Actions..."*
4. Sau 1-2 phút, Bot gửi lại tin nhắn:
   ```text
   🎉 ĐÃ CÀO XONG VÀ ĐỒNG BỘ GOOGLE DRIVE!
   • 🎯 File thành công: 1 file
   • ⏱️ Tổng thời lượng: 101.5s
   • ☁️ Google Drive: ASR_Dataset/Week2/
   ```
5. **Bạn mở Google Drive trên điện thoại là file WAV sạch chuẩn 16kHz Mono đã nằm sẵn ở đó!**
