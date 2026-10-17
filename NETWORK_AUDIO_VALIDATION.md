# Thử tải audio qua WebSocket thật — 2026-10-17

**Không đạt nghiệm thu.** Goal professional vẫn hoạt động; không đổi ngưỡng
60 giây để hợp kết quả. Đây là một lượt chẩn đoán trước khi tối ưu; chưa chạy đủ
ba lượt, chưa đo tám giọng khác nhau hoặc hội trường.

## Phạm vi

`server/evaluate_network_audio.py` khởi động app thật bằng Uvicorn, bind cổng
ngẫu nhiên chỉ trên loopback, mở tám kết nối TCP WebSocket, phát đồng thời PCM
người thật, nhận transcript và kết quả AI. Whisper medium CPU int8, RAG Chroma
thật, embedding ở endpoint review riêng; planner gpt-oss:120b-cloud, composer và
reviewer gemma4:31b-cloud, style technical. Không mock STT hoặc agent.

Cùng đoạn podcast tiếng Việt 516–540 giây được phát lại trên cả tám kết nối.
Nguồn [manifest công khai đã lưu](validation/expert-meeting-2026-10-16/source_manifest.json)
là phỏng vấn Kyons của Vietsuccess; câu hỏi được dùng để hỏi về FPTEELiterature.
Không gọi đó là bản phỏng vấn gốc của FPTEELiterature. Không có lời chuẩn đã
kiểm chứng cho đoạn này, vì vậy không tính WER. Phát lại một đoạn không đo độ
đa dạng nội dung, giọng người, nhiễu hoặc nói chồng.

Máy review Linux có 20 CPU logic, khoảng 15,6 GiB RAM; Python 3.10.20,
faster-whisper 1.0.3, CTranslate2 4.8.3. Không phải phần cứng chuyên dụng cho bài
thử; không suy rộng số đo thành năng lực của mọi máy hoặc mạng WAN.

## Quan sát

| Mục | Kết quả |
| --- | --- |
| Kết nối / lượt | 8 / 1 |
| Nhận processing → transcript → suggestion | 7/8 |
| Lượt còn lại | processing → transcript → error, lỗi giao thức review sau thử lại |
| Request ID trên các sự kiện nhận được | 8/8 đúng |
| Context riêng đang hoạt động / dọn sau disconnect | 8 context / còn 0 |
| p95 end-to-end, gồm cả lượt lỗi | 173,595 giây; mục tiêu ≤60 giây, không đạt |
| STT ở các lượt thành công | 76,067–153,090 giây |
| Agent ở các lượt thành công | 9,738–20,237 giây |
| Transcript | 94 đơn vị cách trắng, cùng hash trên 8 lượt; không chứng minh đúng |

Request ID và số context đúng chỉ xác nhận các thuộc tính đó. Vì audio lặp lại,
không suy ra đã chứng minh không lẫn nội dung ngữ nghĩa giữa các phiên. Không
đánh giá độ đúng câu trả lời trong runner này. Lượt lỗi review không phải lỗi
nhận dạng giọng nói; thời gian STT cho thấy nút thắt lớn dưới tải nằm trước AI.

Kết quả JSON chỉ có số liệu/hash, không chứa audio, transcript, nguồn riêng hay
câu trả lời: [validation/network-audio-2026-10-17](validation/network-audio-2026-10-17).
Log server vẫn có thể chứa transcript nên giữ riêng. Kết nối SSH quan sát bị
reset sau khi chạy; đã đọc báo cáo hoàn chỉnh và log shutdown trên server,
không khởi chạy lại bài thử vì lỗi quan sát.

## Tái lập

Chạy từ `server` trong môi trường review đã cài dependency và model:

```sh
python evaluate_network_audio.py --audio /private/source.mp3 --start 516 --duration 24 --evidence /private/project-evidence-neutral.md --output /private/network.json --sessions 8 --runs 1 --whisper medium --model gpt-oss:120b-cloud --answer-model gemma4:31b-cloud --review-model gemma4:31b-cloud --embedding-url http://127.0.0.1:11436
```

Runner trả exit code khác 0 khi lỗi thực thi hoặc p95 vượt ngưỡng. Nó dùng store
tạm và không sửa dữ liệu dự án thật. Các lượt đo sau phải ghi rõ model, số luồng,
thời lượng, phần cứng và nguồn; đổi model cần đo lại WER trước khi chọn mặc định.
Không dùng cache transcript để tạo kết quả tải đẹp hơn.

## Thay đổi bao quát đi kèm

Sửa `AgentService` để truy xuất cho toàn bộ tối đa tám yêu cầu, thay vì chỉ ba
yêu cầu đầu. Test chứng minh bằng chứng chỉ có ở yêu cầu thứ tám đến composer,
reviewer và evidence trả về; lỗi truy xuất ở phần cuối chặn câu trả lời một phần
và không ghi lịch sử. Tổng 120 regression test qua trên server, 5,047 giây.
Luồng này được dùng trong bài thử mạng, nhưng vẫn cần đánh giá ngữ nghĩa nhiều
phần riêng; không coi truy xuất đủ số lần là trả lời đủ và đúng.
