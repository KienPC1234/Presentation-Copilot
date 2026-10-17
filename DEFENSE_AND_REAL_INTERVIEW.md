# Chuẩn bị phản biện và phỏng vấn bằng bản ghi thật

## Tính năng chuẩn bị

Dashboard có tab **CHUẨN BỊ PHẢN BIỆN**. Nạp đúng tài liệu của sản phẩm vào kho tri thức, nhập tên/mô tả ngắn, chọn 6/9/12 câu và ngôn ngữ. Có thể xem và lưu JSON của bộ câu hỏi.

Mỗi mục có câu hỏi, mục đích, câu hỏi tiếp, checklist chuẩn bị trả lời và ID đoạn tài liệu. Sáu nhóm gồm giá trị sản phẩm, kỹ thuật, bằng chứng, rủi ro, lựa chọn thay thế và vận hành. Chỗ thiếu bằng chứng được đánh dấu; checklist không có nguồn được thay bằng lời nhắc chuẩn bị bằng chứng thay vì giữ câu trả lời model tự đoán.

**Các câu hỏi này do AI tạo để luyện tập, không phải câu hỏi ghi lại từ hội đồng thật.** `evidence_status=cited` chỉ xác nhận model dẫn tới một excerpt đã cung cấp, không chứng minh diễn giải đúng. Người trình bày cần kiểm tra lại checklist.

API được bảo vệ như các endpoint hiện có:

```http
POST /api/defense/prepare
Content-Type: application/json

{"topic":"Sản phẩm của tôi","focus":"Giá trị người dùng và bằng chứng kiểm thử","count":6,"language":"vi"}
```

JSON phản hồi có `question_origin=ai_generated_preparation`, `questions`, `evidence`, `limitations`. Topic được trim và kiểm tra độ dài; count 3–12, ngôn ngữ vi/en. Từ 6 câu trở lên phải có đủ sáu nhóm. Model trả sai schema, trùng câu hoặc bịa ID nguồn sẽ bị từ chối.

WebSocket hỗ trợ `{"type":"set_topic","topic":"Tên và mô tả sản phẩm"}` và trả `topic_set`. Thao tác bắt đầu đề tài mới xóa ngữ cảnh cũ; `clear` cũng xóa đề tài. Đề tài được dùng để neo truy xuất và câu trả lời cho câu hỏi có chủ ngữ chung chung. `/api/simulate` nhận thêm `topic` tùy chọn.

## Bài phỏng vấn mô phỏng thật đã chuẩn bị

- **Đề tài thật:** FPTEELiterature đang có trên cùng server; đọc các đoạn giới hạn từ `index.html` và `api.php`, không đọc database học sinh, khóa hoặc cấu hình bí mật. Bản snapshot có SHA-256 từng tệp và phạm vi dòng.
- **Nguồn giọng thật:** [Apps, Games, & Insights của Android Developers](https://developer.android.com/podcasts/apps-games-insights), tập [Building quality apps with Firebase — Episode 13](https://appsgamesinsights.libsyn.com/building-quality-apps-with-firebase-episode-13). Đối chiếu với [transcript chính thức](https://developer.android.com/static/podcasts/apps-games-insights/transcripts/building-quality-apps-with-firebase.pdf).
- Ba đoạn hỏi do người thật nói: ý nghĩa chất lượng ứng dụng, ưu tiên sửa lỗi so với thêm tính năng, và rủi ro chất lượng khi tăng trưởng. Các đoạn được cắt theo timestamp trong âm thanh gốc, không dịch câu hỏi rồi dùng TTS.
- Bối cảnh gốc là cuộc trò chuyện về ứng dụng/Firebase/Deliveroo, **không phải phỏng vấn FPTEELiterature**. Trong bài mô phỏng, các câu hỏi gốc được chuyển sang bối cảnh sản phẩm FPTEELiterature; câu trả lời do AI của chúng ta gợi ý. Không có ứng viên/người bảo vệ thật được chấm trong thử nghiệm này.
- Audio SHA-256 và timestamp nằm ở `validation/real-interview-2026-10-16/source_manifest.json`. Âm thanh gốc, mã trích đoạn và báo cáo câu trả lời đầy đủ giữ trong `/home/kien/presentation-copilot-review/real-interview/`; không đưa bản ghi hay toàn bộ transcript lên Git.

## Cách chạy lại trên môi trường server

Từ `/home/kien/presentation-copilot-review/server`, khi Ollama embedding riêng đang chạy:

```bash
../.runtime/bin/python rehearse_recorded_interview.py \
  --manifest ../real-interview/manifest.json \
  --model gpt-oss:120b-cloud --embedding-url http://127.0.0.1:11436 \
  --output ../real-interview/results-private.json
```

Runner kiểm tra checksum trước khi dùng audio, nạp snapshot dự án vào Chroma tạm, gọi API chuẩn bị 6 câu, rồi đưa PCM 16 kHz qua WebSocket thật của FastAPI TestClient. Nó dùng Whisper **base/CPU** để phiên âm, agent/cloud model để gợi ý trả lời và kiểm tra chuỗi `processing → transcript → suggestion` cùng request_id.

Audio source và snapshot phải đã tồn tại; manifest công khai chỉ là thông tin xuất xứ, không phải một dataset đầy đủ kèm mã nguồn dự án khác. Checksum giúp phát hiện bản ghi thay đổi/được chèn quảng cáo làm lệch timestamp. Tệp của dự án đang chạy chỉ được đọc; không thay đổi ứng dụng đó.

## Đánh giá và giới hạn

Đã chạy kiểm thử schema/API/metric và browser UI; số liệu lần chạy cuối nằm trong `validation/real-interview-2026-10-16/summary.json`. WER chỉ được tính ở đoạn có reference chép lời đã đối chiếu: **7 từ**, không suy rộng thành độ chính xác chung. Hai đoạn khác kiểm tra từ khóa, không có WER đầy đủ; từ khóa đúng không chứng minh mọi từ đúng.

Kết quả ghi nhận cuối: 46 kiểm thử unit/API đạt; browser đạt trạng thái chờ, tải JSON, lỗi, escape HTML từ model và các độ rộng 320/390/1440 px. Bộ chuẩn bị có đủ 6 nhóm. Ba clip đều trả suggestion với request_id đúng, mọi từ khóa kiểm tra đều xuất hiện; WER đoạn đầu bằng 0 trong lần này. Thời gian phản hồi tương ứng khoảng **4,38 / 6,37 / 5,54 giây**.

Đọc câu trả lời cuối: AI đã gắn chất lượng với học sinh/giáo viên và dữ liệu bài thi, không lấy Firebase làm tính năng của FPTEELiterature hay bịa số đo tải. Tuy nhiên, câu ưu tiên vẫn nghiêng về coi tính năng mới là phần bổ sung; đây là đơn giản hóa chưa đủ tốt vì một tính năng mới có thể thiết yếu. Lời khuyên tăng trưởng còn khá chung. Không chấm các câu này là hoàn toàn đúng/hữu ích chỉ vì giao thức và từ khóa đều đạt.

Thời gian được tính từ lúc gửi cả clip đã thu vào server đến khi có phản hồi, không bao gồm thời gian thu/phát âm thanh, tải model hoặc tạo bộ câu hỏi. Đây là TestClient trong tiến trình, chưa phải Windows WASAPI → mạng → HUD.

Các vòng đầu cho thấy câu trả lời còn chung chung và checklist có thể suy diễn tính năng thiếu hoặc thời gian dung sai chưa có nguồn. Đã đổi outline thành checklist cần kiểm tra, thay nội dung khi không có bằng chứng, bổ sung bối cảnh sản phẩm và yêu cầu không biến mục tiêu chất lượng thành kết quả đã đo. Không coi citation hợp lệ là xác minh mọi nhận định.

Giới hạn hiện tại: chỉ một sản phẩm, ba câu hỏi tiếng Anh, một model cloud; không có bài nói tiếng Việt hay toàn bộ buổi phản biện nhiều người. Các câu này đã được dùng để điều chỉnh prompt nên không phải bộ kiểm tra độc lập. Chưa có chấm điểm câu trả lời của người dùng, bộ đáp án chuẩn được chuyên gia xác nhận, kiểm thử tải hoặc phân tách kho tri thức nhiều sản phẩm. Hãy nạp đúng một phạm vi tài liệu khi luyện một đề tài.

Kiểm tra UI cục bộ tùy chọn: `python scripts/check_defense_ui.py` (cần Playwright và Microsoft Edge). Script kiểm tra loading, lỗi, dữ liệu AI chứa HTML, xuất kết quả và bố cục 320/390/1440 px bằng dữ liệu giả; điều này khác với kiểm thử model/âm thanh thật trên server.
