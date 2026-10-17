# Kiểm tra AI có dẫn chứng — 2026-10-17

## Vòng tiếp theo: điều kiện trong kết luận và độ đúng báo cáo

- Composer/reviewer được yêu cầu đánh giá kết luận đầu câu độc lập: phần sau
  không sửa được một khẳng định đầu câu sai hoặc thiếu điều kiện. Thêm cặp câu
  đúng/sai về clamp công thức và phân biệt bỏ qua truy cập với giới hạn deadline.
- Lần chạy hiệu chỉnh 18/18 khớp kỳ vọng. Hai lượt bộ 8 câu thực tế có 15/16
  không lỗi, p95 28,98 giây; đọc tay vẫn phát hiện lỗi ngữ nghĩa. Hội thoại 7/8
  không lỗi, 10 kiểm tra ngữ cảnh qua; lịch sử sai vẫn làm câu trả lời bị chặn.
- Lỗi còn lọt: tự đặt ngưỡng lỗi 1%, nói demo chứng minh tính đúng chức năng,
  gán nhầm phần mã bị thiếu, công thức ở phần bước thiếu điều kiện ends_at hợp
  lệ. Đề xuất dual-write/rollback chưa đủ chứng minh bảo toàn bài làm mới.
  Đây là bằng chứng chưa đạt; tỷ lệ engine cho qua không đo độ đúng.
- Sửa nguyên nhân ngưỡng 1%: số 1 trần trong mã không được dùng làm nguồn cho
  phần trăm. Không tuyên bố đã kiểm tra toàn bộ phép đổi đơn vị hoặc quan hệ
  hỗ trợ. Thêm một phản ví dụ thành bộ 19 câu: 18 khớp, một câu đúng bị lỗi
  giao thức review; không chạy lại chỉ để thay số thất bại bằng số đẹp.
- 118 regression test qua, 5,262 giây. Các phép đo 16 câu/hội thoại ở trên
  chạy trước sửa phần trăm; giữ báo cáo riêng để không trộn cấu hình.
- Sau sửa phần trăm, chạy riêng câu triển khai hai lượt: 2/2 không lỗi, p95
  10,38 giây, một lượt phải sửa vì ngưỡng tùy ý. Đọc tay: ngưỡng 1% đã biến mất,
  nhưng cả hai vẫn nhầm dừng thử nghiệm khi đạt mục tiêu với dừng mở rộng khi
  có sự cố; phương án migration/dual-write cũng chưa chứng minh giữ dữ liệu.
  Do đó phép thử này **không đạt ngữ nghĩa**, dù execution gate của runner qua.
- Sửa lỗi xuất báo cáo checkpoint trước: tổng 7/8 đã đúng, nhưng cờ lỗi từng
  lượt đọc nhầm `is_error` thay vì trường `error` thật của engine. Hai JSON
  `expert-summary.json` và `conversation-summary.json` đã được đính chính.
  `server/export_evaluation_summary.py` xuất theo danh sách trường cho phép,
  đối chiếu tổng với từng lượt và từ chối báo cáo mâu thuẫn. Không xuất nội dung
  câu trả lời, lỗi riêng, câu hỏi hoặc trace. Thêm test cho lỗi lồng, exception,
  thiếu answer, sai tổng và ngăn nội dung riêng lọt vào bản công khai.

Để xuất số liệu từ báo cáo riêng:

```sh
python export_evaluation_summary.py --input /private/expert.json --output /public/expert-summary.json
```

Các mục dưới đây mô tả checkpoint trước; số liệu mới nằm ở các tệp
`headline-*` và `percent-guard-*` trong cùng thư mục validation. Chưa đóng cổng
nghiệm thu nào chỉ dựa trên vòng này.

**Chưa nghiệm thu professional.** Đây là checkpoint phát triển; tiêu chí trong
[PROFESSIONAL_ACCEPTANCE.md](PROFESSIONAL_ACCEPTANCE.md) vẫn giữ nguyên.

## Thay đổi

Luồng `technical` tách yêu cầu trước khi viết, truy xuất theo các phần của câu hỏi,
rồi kiểm tra mức bao quát và từng trường đầu ra. Khẳng định về dự án cần trích dẫn
nguyên văn từ evidence thật. Parser kiểm tra ID, vị trí trường, đoạn trích và việc
bao phủ toàn bộ nội dung; mô hình vẫn quyết định quan hệ hỗ trợ về ngữ nghĩa.
Không coi sự tồn tại của trích dẫn là chứng minh khẳng định đúng.

Review sai giao thức được thử lại một lần trên cùng câu trả lời và nguồn. Review
âm tính hợp lệ chặn ngay; câu trả lời chỉ được sửa nội dung một lần rồi kiểm lại.
Một review có lỗi rõ ràng được phép từ chối sớm, nhưng muốn duyệt phải đủ toàn bộ
metadata. Nội dung bị chặn không được lưu vào lịch sử.

Thêm kiểm tra hẹp cho ngưỡng thời gian/tỷ lệ mới không có nguồn và kết luận phủ
định toàn bộ trong khi phần khác thừa nhận chưa biết. Đây là các chốt bổ sung,
không thay thế đánh giá chuyên gia. Lưu persona khi bỏ qua ReAct cho câu hỏi chỉ
cần tài liệu; công cụ tính toán và tra cứu web vẫn được định tuyến khi cần.

RAG kết hợp vector và chỉ mục tên hàm/định danh để tìm thân hàm thay vì chỉ điểm
gọi. Chunk mã mang gợi ý phạm vi switch case, giữ nguyên phần mã nguồn. Gợi ý này
là phân tích văn bản, không phải chứng minh bằng AST. Store lỗi không được báo
xóa thành công; store xóa xong được tạo lại để tiếp tục sử dụng.

## Kết quả và giới hạn

| Phép thử | Quan sát | Ý nghĩa |
| --- | --- | --- |
| Backend regression | 113 test qua, 5,516 giây trên môi trường review server | Kiểm tra hợp đồng và logic; không phải độ chính xác AI |
| Bộ phản ví dụ tổng hợp | 14/14 khớp kỳ vọng; 12 gọi reviewer thật, 2 bị chặn xác định | Hiệu chỉnh reviewer trên ví dụ ngắn, không đo chất lượng họp |
| 8 câu chuyên gia, nguồn V2, 8 worker, 1 lượt | 7 được engine cho qua, 1 chặn; p95 toàn bộ 23,59 giây | Còn lỗi thực thi/chất lượng; không phải 87,5% chính xác |
| 8 lượt hội thoại đan xen hai phiên | 7 không lỗi, 1 chặn; 10 kiểm tra ngữ cảnh/reset qua | Chưa đạt yêu cầu không lỗi; chưa thử mạng/audio |

Planner: `gpt-oss:120b-cloud`; composer và reviewer: `gemma4:31b-cloud`.
Composer và reviewer cùng mô hình, không phải xác minh độc lập. Các phép đo model
được chạy trước sửa cuối giữ persona; regression 113 test gồm sửa đó. Chưa có
phép đo model mới cho đúng toàn bộ trạng thái commit này. Không thay đổi client
trong checkpoint này; không tuyên bố đã kiểm thử lại microphone/WPF.

Đọc đối chiếu vẫn thấy kết luận đầu câu quá rộng về bỏ qua `ends_at`, công thức
deadline ở phần tóm tắt thiếu điều kiện dù phần bước giải thích có, và câu hỏi
triển khai từng bước còn bị chặn do metadata review. Lịch sử chứa thông tin sai
có thể làm writer lặp kết luận phủ định quá mức; guard chặn được trường hợp đã
quan sát nhưng chưa tạo ra câu trả lời hữu ích thay thế.

Tám câu `acceptance` đã được đọc và dùng chẩn đoán; từ đây là bộ hồi quy, không
còn là bộ giữ riêng chưa thấy. Luồng `plain` còn dùng review cũ. Chưa có kiểm tra
tải mạng/audio 8 phiên, âm học hội trường/nói chồng, hoặc kiểm toán bảo mật đầy đủ.
RAG chưa có khóa liên process hay ngưỡng liên quan đã hiệu chỉnh.

## Sửa dữ liệu đánh giá

Tài liệu V1 do chúng tôi chuẩn bị có chỉ dẫn và phủ định ngoài đoạn mã, dễ bị
reviewer dùng nhầm làm dữ kiện dự án. Đây là lỗi chuẩn bị dữ liệu đánh giá.
`scripts/prepare_fpte_evidence_v2.py` loại phần dẫn đó, giữ nguyên từng byte của
toàn bộ trích đoạn HTML/PHP và ghi biên nhận hash. V1 vẫn giữ riêng để kiểm toán;
không sửa dự án FPTEELiterature thật. Kết quả V1 và V2 không so sánh trực tiếp.

Hash và số liệu lược dữ liệu riêng nằm trong
[validation/structured-review-2026-10-17](validation/structured-review-2026-10-17).
Không đưa mã nguồn riêng, transcript, audio hay lịch sử giả lập vào báo cáo công khai.
Số đo ASR trước đây trong PROFESSIONAL_VALIDATION.md vẫn là mẫu FLEURS nhỏ,
không phải kết quả âm thanh mới của checkpoint này.

## Tái lập trên môi trường review

Chạy từ thư mục `server`, với dependency và model đã cấu hình:

```sh
python -m unittest discover -s tests
python evaluate_review_quality.py --review-model gemma4:31b-cloud --output /private/calibration.json
python evaluate_expert_meeting.py --evidence /private/project-evidence-neutral.md --model gpt-oss:120b-cloud --answer-model gemma4:31b-cloud --review-model gemma4:31b-cloud --embedding-url http://127.0.0.1:11436 --suite acceptance --workers 8 --runs 1 --output /private/expert.json
python evaluate_conversation.py --evidence /private/project-evidence-neutral.md --model gpt-oss:120b-cloud --answer-model gemma4:31b-cloud --review-model gemma4:31b-cloud --embedding-url http://127.0.0.1:11436 --output /private/conversation.json
```

Báo cáo runner có thể chứa nguồn riêng; chỉ xuất bản bản lược dữ liệu. Bước phát
triển tiếp theo: thống nhất kết luận theo từng yêu cầu để giữ đúng điều kiện và
mức chắc chắn, ổn định luồng này trước khi áp dụng cho `plain`, rồi chạy đủ các
cổng chuyên gia, audio, mạng và bảo mật đã đặt ra.
