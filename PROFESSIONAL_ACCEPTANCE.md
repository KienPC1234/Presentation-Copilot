# Goal: phiên bản dùng chuyên nghiệp

Trạng thái: **đang phát triển, chưa nghiệm thu**. Phạm vi nghiệm thu đầu tiên là
trợ lý cho người lớn trình bày sản phẩm, trả lời tiếng Việt rõ ràng, trong luồng
một người nói mỗi lượt. Hội trường nhiều micro/nói chồng phải có thử nghiệm
riêng; không được suy ra từ kiểm thử nhiều phiên agent.

## Các cổng nghiệm thu

| Cổng | Điều kiện trước khi đánh dấu đạt | Trạng thái hiện tại |
| --- | --- | --- |
| Độ đúng chuyên gia | Bộ phát triển và bộ giữ riêng, mỗi bộ ít nhất 8 câu; 2 lượt chạy; đọc đối chiếu nguồn, không còn lỗi nghiêm trọng về dữ kiện, bảo mật hay chính sách | Chưa đạt |
| Bao quát và ngôn ngữ | Mỗi yêu cầu con có đáp án hoặc ghi rõ chưa biết; không lẫn ngôn ngữ, không biến đề xuất thành tính năng đang có | Chưa đạt |
| Hội thoại | Hỏi nối tiếp, đổi chủ đề, reset, lịch sử chứa khẳng định sai; kiểm tra không dùng câu trả lời cũ làm bằng chứng | Chưa chạy đủ |
| Âm thanh | Ít nhất 10 đoạn tiếng Việt người thật có lời chuẩn; báo WER theo từng đoạn và tổng; mục tiêu WER tổng ≤15% âm thanh sạch, ≤25% nhiễu thử nghiệm đã ghi cách tạo | Medium đạt trên mẫu FLEURS nhỏ: 11,55% / 14,52%; chưa nghiệm thu âm học họp |
| Nhiều phiên | 8 phiên độc lập, 3 lượt; không lẫn dữ liệu/request ID; không lỗi thực thi; p95 trả lời văn bản ≤45 giây và audio ≤60 giây trên môi trường công bố | Đã thử mạng loopback 8 audio × 1: 7/8 gợi ý, ID đúng, p95 173,595 giây; chưa đạt, chưa đủ 3 lượt/đa giọng |
| An toàn, dữ liệu | Auth/Origin, dữ liệu lỗi không vào lịch sử, lỗi RAG không biến thành thiếu tài liệu, nguồn bị xóa không còn trả về, ingest/query nhất quán, đầu ra lỗi được chặn | 77 kiểm thử qua; nguồn xóa được xử lý khi nạp lại phạm vi; chưa có bảo đảm đa process |
| Bàn giao | Hồi quy backend/client, build, hướng dẫn cấu hình, báo cáo lỗi còn mở, lệnh tái lập, ghi rõ giới hạn và commit được push | Đang làm |

Các ngưỡng trên là mục tiêu kỹ thuật đặt trước cho vòng nghiệm thu này, không
phải số đo đã đạt hoặc cam kết cho mọi phần cứng. Không dùng tỷ lệ câu trả lời
đúng JSON, từ khóa hay lời tự đánh giá của mô hình làm tỷ lệ chính xác ngữ nghĩa.

Checkpoint mới nhất: [NETWORK_AUDIO_VALIDATION.md](NETWORK_AUDIO_VALIDATION.md):
120 test backend qua; truy xuất cả tám yêu cầu; thử audio mạng chưa đạt độ trễ.
Vòng nội dung: [STRUCTURED_AI_REVIEW.md](STRUCTURED_AI_REVIEW.md): 118 test
backend qua; chuyên gia V2 hai lượt 15/16 và hội thoại 7/8 không lỗi, nhưng đọc
tay còn lỗi ngữ nghĩa. Review cuối 18/19 trên ví dụ tổng hợp; chưa đủ nghiệm thu.
Các cổng trên vẫn mở. Số 77 test trong bảng là mốc trước; kết quả ASR và tải
trước đó: [PROFESSIONAL_VALIDATION.md](PROFESSIONAL_VALIDATION.md).

## Chu kỳ thực hiện

1. Giữ nguyên dữ liệu và câu hỏi gây lỗi, sửa nguyên nhân, thêm kiểm thử phù hợp.
2. Chạy lại tập phát triển bằng engine thật và đọc đối chiếu bằng chứng.
3. Chạy bộ giữ riêng sau khi ổn định để hạn chế sửa theo đúng câu đã biết.
4. Đánh giá nghe, hội thoại, tải và bảo mật; lưu dữ liệu riêng ngoài Git.
5. Cập nhật bảng đạt/chưa đạt và báo cáo, push thay đổi có ghi chú.

Lớp rà soát bằng mô hình là một phép kiểm bổ sung có giới hạn, vẫn có thể bỏ
sót hoặc từ chối nhầm. `review_status=model_reviewed` không có nghĩa sự thật
đã được xác minh độc lập. Nội dung bị từ chối sau một lần sửa không được ghi
vào lịch sử. Không đổi trạng thái goal thành hoàn tất khi còn cổng chưa đạt.
