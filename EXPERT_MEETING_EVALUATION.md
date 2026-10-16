# Đánh giá tiếng Việt ở mức chuyên gia — 16/10/2026

## Kết quả và quyết định

**Chưa đủ điều kiện dùng tự tin trong cuộc họp chuyên gia.** Chạy mô hình thật
`gpt-oss:120b-cloud`, RAG thật trên bản chụp mã FPTEELiterature, 8 câu hỏi tiếng
Việt do người phát triển soạn, theo các vai trò CTO, giáo viên, bảo mật, vận hành,
tài chính, sản phẩm, chủ trì và người phản biện. Tối đa 4 phiên agent độc lập
xử lý đồng thời; đây không phải thử phòng họp có 8 người nói hoặc thử tải mạng.

Trước sửa: 4/8 câu trả lời hợp lệ, cả lượt 14,07 giây. Sau sửa: 8/8 hợp lệ,
cả lượt 19,16 giây, từng câu 5,81–10,99 giây. Đây là tính hợp lệ cấu trúc,
**không phải độ chính xác nội dung** và không đủ mẫu suy rộng hiệu năng.

## Thay đổi

Chế độ technical nay cũng qua bước soạn JSON từ bằng chứng gốc và quan sát công
cụ, thay vì phụ thuộc hoàn toàn vào đầu ra ReAct. Nếu planner lỗi, vẫn có thể
soạn từ bằng chứng đã truy xuất; lỗi truy xuất vẫn dừng xử lý. Giữ phong cách
plain mặc định. Bổ sung chỉ dẫn trả đủ các ý, tiếng Việt theo câu hỏi, phân biệt
mã nguồn / hành vi chưa đo / đề xuất kiểm thử. 47 kiểm thử hồi quy qua trên server.

## Lỗi nội dung còn mở sau sửa

- Bảo mật: biến yêu cầu thử sửa ID thành hướng dẫn quy trình cập nhật và giả
  định endpoint tồn tại. Cần trả ma trận thử quyền sở hữu, không bịa API.
- Giáo viên: nói quy trình thông báo và quyền giải trình như tính năng đã có;
  cần ghi đó là chính sách đề xuất, chưa được chứng minh bởi tài liệu.
- Sản phẩm: một phần câu trả lời lẫn chữ Trung Quốc.
- Firebase: mở đầu đúng là chưa có bằng chứng, nhưng bước cuối lại kết luận
  không dùng. Thiếu bằng chứng không chứng minh không tồn tại.
- Chủ trì: nhầm điều kiện kết thúc kỳ thi với điều kiện dừng triển khai toàn
  trường. Cần tiêu chí triển khai về dữ liệu, bảo mật, khôi phục và trách nhiệm.

Không chấm tỷ lệ chính xác bằng từ khóa. Các lỗi trên được đọc và đối chiếu
thủ công; gắn nguồn truy xuất cũng không chứng minh mọi mệnh đề được nguồn hỗ trợ.

## Âm thanh tiếng Việt thật

Nguồn: Vietsuccess, The Quoc Khanh Show #46, Quốc Khánh phỏng vấn Nguyễn Thanh
Tú (Kyons), lấy enclosure từ RSS chính thức được Apple Podcasts trỏ tới.
Trang nhà phát hành: https://vietsuccess.asia/podcasts/ ; RSS:
https://anchor.fm/s/1081bb15c/podcast/rss . URL, SHA-256 và mốc cắt nằm trong
`validation/expert-meeting-2026-10-16/source_manifest.json`.

Phát lại đoạn 516–540 giây, người thật hỏi làm rõ sản phẩm, qua WebSocket thực
trong TestClient: processing → transcript → suggestion, đúng request ID.
Whisper base, ngôn ngữ vi; thời gian backend khoảng 11,33 giây. Nhận được hai
cụm từ kiểm tra nhưng bản nhận dạng có lỗi rõ ràng. Không có bản tham chiếu đã
kiểm chứng nên **không báo WER hoặc độ chính xác tiếng Việt**. Đoạn cắt có thể
chứa cả phần dẫn/đáp, chưa phải tập câu hỏi đã căn chỉnh thủ công hoàn chỉnh.
Câu hỏi gốc về Kyons được chuyển ngữ cảnh sang FPTEELiterature; không phải
phỏng vấn gốc về FPTEELiterature. Không dùng TTS, không đăng lại audio/transcript.

## Tái lập

Chạy từ server/, dùng đường dẫn bằng chứng và báo cáo riêng ngoài Git:

```sh
python evaluate_expert_meeting.py --evidence /private/project-evidence.md --output /private/expert.json --model gpt-oss:120b-cloud --embedding-url http://127.0.0.1:11436 --workers 4 --style technical
python rehearse_recorded_interview.py --manifest /private/manifest.json --output /private/audio.json --model gpt-oss:120b-cloud --embedding-url http://127.0.0.1:11436 --language vi --whisper-model base --style technical
```

Bộ phát lại nay cho chọn ngôn ngữ, model Whisper và phong cách. Để tái lập bài
tiếng Anh trước đây, truyền `--language en`. Báo cáo thô có thể chứa mã/tài liệu
riêng và phải nằm ngoài Git; chỉ số công khai đã lược nội dung nằm ở thư mục
validation. Chưa kiểm tra nói chồng, nhiều micro, tiếng vọng, người nói, phiên
hỏi nối tiếp dài hoặc độ trễ qua mạng thật. Không kết luận sẵn sàng họp lớn.
