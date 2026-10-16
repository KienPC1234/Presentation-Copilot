# Cập nhật: bảo mật, độ ổn định và kiểm tra logic AI

## Chuẩn bị phản biện và bài phỏng vấn ghi âm thật — 2026-10-16

Thêm tab dashboard và API `/api/defense/prepare` cho bộ câu hỏi theo sáu nhóm, nguồn tham khảo và checklist chuẩn bị; phân biệt rõ câu AI tạo với câu hỏi lịch sử. WebSocket có `set_topic`, simulation nhận đề tài để neo ngữ cảnh. Thêm runner replay giọng người thật, manifest nguồn/hash/timestamp, metric WER chỉ khi có reference và bộ test schema/API/UI. Bài chạy dùng sản phẩm FPTEELiterature trên server cùng ba đoạn hỏi từ podcast chính thức Android Developers. Xem `DEFENSE_AND_REAL_INTERVIEW.md` cho dữ liệu, kết quả, hạn chế và cách chạy lại.

## Trả lời dễ hiểu cho người lớn — 2026-10-16

Mặc định `RESPONSE_STYLE=plain`: nói ngắn, từ quen thuộc, giữ số liệu và mức chắc chắn; có `technical` để chọn cách nói chuyên môn. Thêm bước biên soạn cuối dựa trên evidence, kiểm tra ví dụ với tối đa một lần sửa và bộ lọc hẹp cho chỉ dẫn ghi đè prompt trong tài liệu. Đã chạy so sánh 10 câu trước/sau, nhóm câu mới và regression, cùng 30 kiểm thử logic trên server. Xem `PLAIN_LANGUAGE_EVALUATION.md` và dữ liệu gốc; có ghi cả lỗi còn lại, chi phí thời gian và giới hạn của phép đánh giá.

## Kiểm thử server bổ sung — 2026-10-16

Đã chạy trên môi trường riêng: 16 kiểm thử đạt, embedding Ollama + Chroma thật, agent cloud với ba case giả lập, Whisper tiny trên CPU và toàn luồng WebSocket bằng FastAPI TestClient. Sửa parser ReAct để nhận JSON hợp lệ trực tiếp và bổ sung cấu hình `OLLAMA_EMBEDDING_BASE_URL`. Thêm `runtime_smoke.py`, `protocol_smoke.py` và kết quả gốc. Xem `SERVER_VALIDATION.md` để biết lỗi môi trường, thời gian quan sát và phạm vi chưa kiểm chứng. Các mục giới hạn bên dưới mô tả mốc cập nhật ban đầu.

## Thay đổi hành vi

- API/WebSocket mặc định chỉ nhận kết nối cục bộ; hỗ trợ bearer token, kiểm tra Origin/Host và giới hạn buffer âm thanh. Docker yêu cầu API_TOKEN.
- Loại công cụ shell khỏi agent; giới hạn biểu thức calculator và escape dữ liệu động trên dashboard.
- Client dùng request_id để ghép phản hồi, giữ trạng thái bận đến khi nhận kết quả, xử lý heartbeat riêng và có thời hạn chờ.
- Server gửi transcript trước kết quả AI, kèm số đo thời gian xử lý.
- Chuyển đổi âm thanh bằng Media Foundation để có lọc chống aliasing; sửa vòng đời capture và resampler.
- Lưu cấu hình theo người dùng; áp dụng endpoint và thời lượng buffer sau khi lưu.
- RAG dùng ID ổn định, cập nhật các chunk của tệp đã ingest và hiển thị nguồn liên quan/PDF page khi có.
- Agent nhận evidence trước khi sinh câu trả lời. Nguồn trả về dựa trên evidence thực nhận, không truy xuất thêm sau câu trả lời để gán nguồn.
- Parser dùng chung kiểm tra JSON và kiểu dữ liệu; từ chối đầu ra hỏng/hết vòng lặp, loại trường giao thức hoặc nguồn do model tự thêm.
- Lỗi AI không được ghi vào lịch sử; lỗi STT/RAG không còn bị coi là không có dữ liệu. Sửa persona chứa ngoặc nhọn, kiểm tra persona và giới hạn lịch sử.

## Thay đổi cần lưu ý khi chạy

- Trigger WebSocket cần request_id: `{"type":"trigger","request_id":"unique-id"}`.
- Khi dùng token, đặt API_TOKEN cho server và PRESENTATION_COPILOT_API_TOKEN cho Windows client. Dashboard hỏi token khi cần.
- Docker Compose yêu cầu API_TOKEN trong server/.env; các port được publish trên loopback.
- Cấu hình người dùng lưu tại `%LOCALAPPDATA%/PresentationCopilot/appsettings.json`.

## Đã kiểm tra

- Client .NET build thành công: 0 lỗi, 0 cảnh báo.
- 13 kiểm thử logic đạt: 10 cho AI/context/orchestration, 3 cho chính sách truy cập.
- Python compileall, kiểm tra cú pháp JavaScript dashboard và git diff --check đạt.

## Giới hạn và công việc tiếp theo

Chưa chạy tích hợp bằng mô hình Ollama/Whisper và Chroma thực. Các kiểm thử orchestration dùng provider giả; không phải đánh giá độ chính xác câu trả lời. Transcript sớm chưa phải streaming STT/token liên tục. Nguồn liên quan chưa chứng minh từng nhận định. Chưa có ngưỡng liên quan RAG, tự loại tệp đã xóa, hoặc đánh giá chất lượng bằng tập câu hỏi/âm thanh chuẩn.

Xem AI_ENGINE_REVIEW.md cho phát hiện và ưu tiên; DEVELOPMENT.md cho các mốc tiếp theo; server/benchmark.py để đo trên máy có đủ môi trường AI.
