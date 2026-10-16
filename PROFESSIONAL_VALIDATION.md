# Vòng phát triển–nghiệm thu 17/10/2026

**Kết luận: tiếp tục phát triển, chưa nghiệm thu professional.** Goal và các
cổng nghiệm thu nằm trong [PROFESSIONAL_ACCEPTANCE.md](PROFESSIONAL_ACCEPTANCE.md).
Số liệu công khai, đã bỏ câu trả lời riêng và trích đoạn mã dự án, nằm trong
[summary.json](validation/professional-2026-10-17/summary.json).

## Đã thay đổi và kiểm tra

- Thêm rà soát câu trả lời theo câu hỏi, bằng chứng gốc và quan sát công cụ.
  Nếu có vấn đề, sửa tối đa một lần rồi rà soát lại; câu vẫn lỗi không được
  hiển thị như suggestion thành công hay ghi vào lịch sử. Có kiểm tra hẹp cho
  chữ Trung Quốc ngoài yêu cầu, phủ định công nghệ, đường dẫn bịa và chính sách
  chưa có nguồn. Các kiểm tra này có thể bỏ sót hoặc từ chối nhầm.
- Phát hiện adapter LangChain đang cài không chuyển tham số `think` tới Ollama.
  Thêm client JSON không streaming để yêu cầu final content, giới hạn kích thước,
  từ chối đầu ra bị cắt/rỗng, và đặt timeout 45 giây cho từng lời gọi. Đây chưa
  phải deadline cho toàn lượt hỏi. Không đưa reasoning trace vào đầu ra.
  API theo [tài liệu Ollama](https://docs.ollama.com/api/chat).
- Cho chọn riêng mô hình soạn và rà soát; chỉ dẫn technical được tách khỏi
  các quy tắc plain để giảm lặp nội dung hướng dẫn trong câu trả lời.
- Nạp lại một thư mục sẽ loại các chunk của tệp đã xóa/rỗng trong đúng phạm vi;
  không xóa dữ liệu của phạm vi khác. Đọc lỗi hủy nạp trước khi sửa chỉ mục.
  Khóa tuần tự bảo vệ ingest/query/clear trong **một instance**, và marker trên
  đĩa chặn truy xuất sau cập nhật dở dang, kể cả khởi động lại.
- Mỗi kết nối WebSocket có ID riêng, không dùng địa chỉ/port làm khóa phiên.
  Đã thử 8 kết nối cùng peer bằng TestClient: topic riêng, reset riêng, dọn phiên.
  Bài này dùng giao thức thật nhưng không gọi STT/AI, không thay cho thử mạng.
- Lưu thêm các ý trả lời để hỏi tiếp; giới hạn lịch sử đưa vào prompt ở 24.000
  ký tự, giữ nguyên việc mã hóa từng lượt. Lịch sử không trở thành bằng chứng.
- Simulation trả đúng các đoạn agent thực sự quan sát, bỏ lượt truy xuất riêng
  có thể khác phiên bản dữ liệu; lỗi tạo câu trả lời trả HTTP 502.
- Cấu hình STT được snapshot theo lượt và kiểm tra mã ngôn ngữ/prompt. Origin
  sai định dạng và bearer có Unicode không còn gây ngoại lệ của chính sách auth.

**77/77 kiểm thử backend qua trên server**, gồm vòng đời Chroma thật với embedding
xác định, lỗi ghi/khởi động lại, khóa đọc–ghi, auth, phiên, cấu hình, parser và
orchestration. Các kiểm thử provider dùng mock; mô hình thật được đo riêng bên dưới.
Client .NET build lại thành công với `--no-restore`: 0 lỗi, 0 cảnh báo; đây là
kiểm tra biên dịch, chưa phải chạy micro/WPF trong phòng họp. Python compileall
và git diff --check qua; các JSON công khai không chứa trường câu trả lời riêng,
transcript, candidate hay trích đoạn nguồn.

## Âm thanh có lời chuẩn

Nguồn [Google FLEURS](https://huggingface.co/datasets/google/fleurs), CC BY 4.0,
revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, `vi_vn/test`.
Chọn **12 dòng đầu TSV trước khi nhận dạng**, tương ứng **5 câu khác nhau**,
303 đơn vị tách theo khoảng trắng sau chuẩn hóa. Đây là giọng người đọc có lời
chuẩn; không phải 12 câu phỏng vấn khác nhau hay mẫu đại diện cho cuộc họp.

| Model / điều kiện | Số lỗi / 303 đơn vị | WER tổng | Trung vị thời gian / đoạn |
| --- | --- | --- | --- |
| base, nguyên bản | 142 | 46,86% | 1,63 giây |
| small, nguyên bản | 78 | 25,74% | 4,09 giây |
| medium, nguyên bản | 35 | 11,55% | 11,08 giây |
| medium, thêm nhiễu Gaussian 15 dB | 44 | 14,52% | 10,71 giây |

Thời gian đo trên CPU của server dùng chung, không gồm tải model lúc khởi động;
không suy ra hiệu năng trên mọi máy. Nhiễu được tạo xác định với seed 20261016 +
chỉ số đoạn, theo công suất RMS; không mô tả đó là tiếng ồn họp thật. Giữ dấu
tiếng Việt, chuẩn hóa chữ thường/dấu câu; WER này tính theo đơn vị chữ cách nhau,
không phải bộ tách từ ngôn ngữ học. Chi tiết từng đoạn và hash ở các JSON ASR.

Medium đạt mục tiêu số học của cổng ASR **trên mẫu nhỏ này**; vẫn cần phỏng vấn
tự nhiên, tên riêng, số liệu, giọng vùng miền và âm học phòng họp. Không đổi model
mặc định base; muốn dùng medium cần cấu hình `WHISPER_MODEL_SIZE=medium` rồi
khởi động lại server, chấp nhận chi phí thời gian/tài nguyên đã đo.

## Phản biện chuyên gia và tải

Cấu hình thử: planner `gpt-oss:120b-cloud`, soạn `deepseek-v4.1-flash:cloud`,
rà soát `gemma4:31b-cloud`; bằng chứng FPTEELiterature cùng hash của vòng trước.
Không thay dịch vụ FPTEELiterature hoặc Ollama dùng chung. Đây là 8 luồng agent
trên cùng corpus, không phải nhiều tenant, tải WebSocket mạng hay hội trường.

| Thử | Câu trả lời được engine cho qua | Bị chặn/lỗi | p95 mọi lượt |
| --- | --- | --- | --- |
| Phát triển: 8 câu × 2 lượt | 16/16 | 0 | 26,00 giây |
| Bộ ban đầu dành giữ riêng, nay dùng hồi quy: 8 câu × 3 lượt | 21/24 | 3 | 34,88 giây |

p95 dùng nearest rank và tính cả lượt bị chặn. **Engine cho qua không có nghĩa
đúng ngữ nghĩa.** Đọc tay vẫn phát hiện:

1. Một câu vận hành gán `replayed=true` cho `submission_status`, trong khi đoạn
   mã đặt trường đó ở nhánh `submit_exam`.
2. Câu bảo mật có lúc thiếu phép thử sửa ID và chuyển thành hướng dẫn giữ/đổi
   định danh; có câu nói không thể sửa tùy ý mà chưa có bằng chứng kiểm thử.
3. Có lúc nhầm bằng chứng upsert bản nháp với bảo đảm chống trùng bài nộp cuối,
   hoặc thiếu các mốc trước/sau deadline và hành vi dùng lại bản nháp.
4. Key point từng khẳng định quyền giải trình như chính sách đang có. Đã thêm
   guard và chạy tập trung 2 lượt: cả hai đã nói rõ chưa có trong bằng chứng.
5. Guard phủ định công nghệ từng chặn nhầm câu trả lời đúng về Kafka. Đã thu hẹp
   về khẳng định trực tiếp; 2 lượt tập trung sau sửa đã cho câu trả lời phù hợp.
   Lượt lỗi thứ ba là `framework_steps` sai schema; chưa có sửa được kiểm lại
   cho ca này.

Các sửa sau bài toàn bộ chỉ mới được kiểm lại tập trung; **chưa được nâng kết quả
toàn bộ thành đạt**. Bộ giữ riêng nay đã được đọc để sửa lỗi, nên khi cần đánh
giá tổng quát mới phải có một bộ giữ riêng khác. Hướng tiếp theo là phân rã yêu
cầu con và liên kết từng nhận định với đoạn nguồn, thay vì chỉ thêm chỉ dẫn.

5 ca hồi quy plain bằng mô hình thật đã trả lời phù hợp khi đọc tay: tiếng Anh,
tính giờ, không suy ra tự xóa, ví dụ đời thường và hai nguồn mâu thuẫn. Đây là
bằng chứng hẹp, không phải tỷ lệ chính xác tổng thể.

## Phát lại phỏng vấn tiếng Việt

Dùng bản ghi Vietsuccess/Kyons và mốc 516–540 giây đã công bố trong manifest
vòng trước. Với medium, chạy thật qua TestClient/WebSocket thu được đúng chuỗi
processing → transcript → suggestion và request ID. STT **23,652 giây**, agent
**15,005 giây**, tổng **38,657 giây**. Không có lời chuẩn đã kiểm chứng cho đoạn
này nên không báo WER; không lấy từ khóa làm điểm chính xác. Đây là kiểm tra một
lượt, chưa phải nghiệm thu độ đúng trên toàn cuộc phỏng vấn hay 8 audio đồng thời.

## Tái lập và vận hành an toàn dữ liệu

```sh
# Đứng ở thư mục repo; ghi dữ liệu có audio/transcript ngoài Git.
python scripts/fetch_fleurs_vi.py --output-dir /private/fleurs-vi --count 12
cd server
python evaluate_vietnamese_asr.py --manifest /private/fleurs-vi/manifest.json --output /private/medium.json --whisper-model medium
python evaluate_vietnamese_asr.py --manifest /private/fleurs-vi/manifest.json --output /private/medium-noise.json --whisper-model medium --noise-snr-db 15
python evaluate_expert_meeting.py --evidence /private/project-evidence.md --output /private/expert.json --model gpt-oss:120b-cloud --answer-model deepseek-v4.1-flash:cloud --review-model gemma4:31b-cloud --embedding-url http://127.0.0.1:11436 --workers 8 --suite holdout --runs 3
python -m unittest discover -s tests
```

CLI trả mã thoát 1 khi có câu bị chặn/lỗi, vẫn lưu báo cáo. `--case` hỗ trợ chẩn
đoán tập trung; `--trace-review` ghi candidate và phản hồi JSON của reviewer vào
**báo cáo riêng**, không ghi reasoning trace hay đẩy báo cáo đó lên Git.

Chạy một server worker cho mỗi thư mục Chroma; khóa hiện tại không phối hợp
nhiều process. Sau sự cố marker `needs_rebuild`, dùng clear-vectors rồi nạp lại
**tất cả phạm vi nguồn**, không chỉ tệp vừa lỗi. Clear xóa toàn bộ chỉ mục nhưng
không xóa tài liệu nguồn. Không tự xóa marker để cho qua dữ liệu dở dang. Chưa có
watcher tự đồng bộ khi tệp nguồn thay đổi; cần nạp lại đúng phạm vi.

Các model cloud nhận câu hỏi và đoạn tài liệu được cung cấp. Vòng thử chỉ dùng
snapshot đã chọn, không cấu hình/khóa hoặc dữ liệu học sinh. Các model mặc định
trong `.env.example` chưa được chứng nhận bởi các kết quả của tổ hợp cloud này.
