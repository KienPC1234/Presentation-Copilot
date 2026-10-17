"""New developer-authored acceptance questions; not historical interview quotes.

Freeze before first evaluation. Source snapshot semantics are adjudicated
manually, not with keyword matches or the model's own approval flag.
"""

ACCEPTANCE_CASES = [
    ("draft_access_deadline", "Khi đã có bản nháp, điều kiện kiểm tra mã phòng và ends_at thay đổi thế nào, và deadline cá nhân vẫn được tính ra sao? Phân biệt các nhánh, đừng suy ra được làm bài mãi."),
    ("callee_body_missing", "Chỉ thấy lời gọi saved_submission_result(user_id, exam_id, key) thì đã chứng minh quyền sở hữu bài làm chưa? Tách điều biết từ lời gọi, điều cần xem trong thân hàm và phép thử cần làm."),
    ("empty_submission_key", "submission_key là chuỗi rỗng thì submission_status và submit_exam có cùng kiểm tra regex không? Đối chiếu riêng từng điều kiện đã được trích; không đoán phần mã còn thiếu."),
    ("deadline_calculation", "Giả định started_at=1000, duration=0 và ends_at không parse được. Theo công thức trong đoạn mã, deadline_epoch bằng bao nhiêu và vì sao? Không coi đây là số đo trên môi trường thật."),
    ("timestamp_race", "UPDATE started_at có điều kiện started_at=0 đã chứng minh toàn bộ luồng nộp bài chống tranh chấp chưa? Nêu phạm vi bảo vệ thực sự của câu lệnh và bằng chứng cần bổ sung."),
    ("strict_deadline_boundary", "Xét riêng nhánh chọn answers đã trích: tại time() bằng deadline+15 và bằng deadline+16, lấy đáp án từ yêu cầu hay bản nháp? Giải thích dấu so sánh, không lẫn với lỗi kiểm tra sớm hơn."),
    ("demo_not_service_proof", "Demo trên một máy chạy tốt có đủ suy ra p99 hoặc uptime 99,99% không? Đề xuất các chỉ số và cách thu bằng chứng trước khi triển khai, không tự đặt ngưỡng mới."),
    ("staged_rollout_preserve_new_work", "Đề xuất triển khai thử ở một lớp rồi mở rộng dần: khi nào dừng, ai xác nhận và quay lại bản cũ thế nào để không mất bài làm mới phát sinh? Tách đề xuất khỏi tính năng đã có bằng chứng."),
]
