# Kiểm thử trên server — 2026-10-16

## Môi trường và phạm vi

- Kết nối bằng SSH alias `toxahoi-server`; bản làm việc riêng: `/home/kien/presentation-copilot-review`.
- Python 3.10 trong `.runtime`, cài đủ `server/requirements.txt`; `pip check` đạt. Không sửa môi trường FPTEELiterature và không cần sudo.
- Sinh câu trả lời: `gpt-oss:120b-cloud` qua Ollama đang có ở `127.0.0.1:11434`. Chỉ gửi dữ liệu giả lập và transcript của mẫu tiếng Anh công khai.
- Embedding: `nomic-embed-text` trên CPU, Ollama riêng ở `127.0.0.1:11436`. Bản Ollama dùng chung liệt kê model nhưng embedding lỗi 500 vì thiếu `llama-server`; không thay đổi dịch vụ dùng chung.
- Đã tải [gói Ollama v0.34.1 chính thức](https://github.com/ollama/ollama/releases/tag/v0.34.1), xác minh SHA-256 theo checksum phát hành và giải nén trong `tools/ollama-runtime`. Tiến trình riêng dùng kho model hiện có, không cần tải lại embedding.

## Lỗi ứng dụng phát hiện và sửa

ReAct parser mặc định từ chối JSON trực tiếp dù schema hợp lệ, dẫn đến hết ba vòng lặp. `StructuredReActParser` hiện nhận JSON đã qua validator như final answer, đồng thời giữ xử lý ReAct action/final envelope. Không cứu JSON bị cắt hoặc trộn suy luận.

Quan sát đầu ra thực tế còn thấy dàn ý tự thêm endpoint refresh không có trong fixture. Prompt đã được bổ sung yêu cầu mọi trường đều có bằng chứng, dàn ý dùng để trả lời câu hỏi và đề xuất phải được ghi rõ. Đây là giảm thiểu bằng prompt; chưa phải kiểm chứng ngữ nghĩa tự động. Một số lời khuyên làm mới token vẫn có thể xuất hiện dù fixture chỉ nói thời hạn; không kết luận đã loại bỏ hoàn toàn suy diễn thiếu nguồn.

Thêm `OLLAMA_EMBEDDING_BASE_URL` để cấu hình embedding riêng mà không thay endpoint sinh câu trả lời. Để trống giữ hành vi cũ.

## Kết quả

| Kiểm tra | Kết quả |
| --- | --- |
| Unit/contract tests trên server, có LangChain thật cho parser | 16/16 đạt |
| Cài gói và Python compileall | Đạt |
| Ingest hai lần với embedding thật và Chroma | Số chunk không tăng |
| Truy xuất fixture Harbor | Lấy được dữ kiện token 17 phút |
| Persona chứa `{project}` | Tạo executor thành công |
| Câu hỏi nhiều phần | Key point đúng 17 phút và lưu queue 9 ngày |
| Câu hỏi throughput không có trong tài liệu | Không bịa RPS; báo thiếu benchmark |
| Câu hỏi tiếng Việt | Key point tiếng Việt, đúng 17 phút |
| Thời gian agent của ba case cuối | 1,16 / 1,97 / 1,46 giây; không phải benchmark ổn định |
| Whisper tiny/CPU với hai giây im lặng | Transcript rỗng |
| Whisper tiny/CPU với `openai/whisper/tests/jfk.flac` | Có transcript, đạt ba từ khóa kiểm tra; khoảng 2,07 giây |
| Toàn luồng qua FastAPI TestClient | `processing → transcript → suggestion`, cùng request_id; lần cuối khoảng 2,75 giây |

JSON gốc và phiên bản gói nằm trong `validation/server-2026-10-16/`.

## Chạy lại

Trong thư mục server của bản làm việc riêng, khi embedding endpoint riêng đang hoạt động:

```bash
../.runtime/bin/python runtime_smoke.py --model gpt-oss:120b-cloud \
  --embedding-url http://127.0.0.1:11436 --output ../runtime-smoke.json

../.runtime/bin/python protocol_smoke.py --audio ../fixtures/jfk.flac \
  --model gpt-oss:120b-cloud --embedding-url http://127.0.0.1:11436 \
  --output ../protocol-smoke.json
```

Mẫu âm thanh công khai lấy từ `https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac`.

Ollama riêng không đăng ký tự khởi động. Binary nằm tại `tools/ollama-runtime/bin/ollama`; tiến trình chạy với `OLLAMA_HOST=127.0.0.1:11436`, `OLLAMA_MODELS=/usr/share/ollama/.ollama/models`, log và PID nằm trong bản làm việc riêng.

## Chưa được kiểm chứng

Chưa chạy WPF/âm thanh WASAPI qua mạng, Qwen local, Whisper base, bản ghi tiếng Việt, tải nhiều phiên, đánh giá WER/recall/precision hoặc kiểm chứng từng nhận định bằng nguồn. TestClient chạy giao thức trong tiến trình, không thay cho kiểm thử kết nối Windows → server. Chroma hiện có cảnh báo telemetry do API posthog không tương thích và cảnh báo wrapper deprecated; các phép ingest/query vẫn đạt, nhưng cần xử lý dependency trước khi phát hành production.
