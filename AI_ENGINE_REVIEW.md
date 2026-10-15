# Rà soát logic AI engine

Phạm vi: STT, RAG, ReAct agent, LLMService dự phòng, đầu ra, ngữ cảnh và giao thức server. Đây là kiểm tra mã và kiểm thử logic bằng mô phỏng; không phải phép đo độ chính xác của mô hình.

## Các lỗi đã sửa

- Parser trước đây cứu JSON hỏng bằng regex, có thể hiển thị thông báo hết vòng lặp hoặc một phần suy luận như câu trả lời. Parser dùng chung hiện yêu cầu JSON hoàn chỉnh, kiểm tra kiểu/độ dài, loại trường thừa và từ chối đầu ra sai cấu trúc. Không tự khôi phục câu trả lời thiếu dữ liệu.
- Agent trước đây có thể bỏ qua RAG; nguồn trong phản hồi lại được tìm sau khi trả lời. Hiện truy xuất được thực hiện trước khi tạo câu trả lời và nguồn được lấy từ evidence đã cấp cùng kết quả công cụ RAG thực sự quan sát được. Đây là nguồn liên quan, chưa phải chứng minh cho từng nhận định.
- Nội dung persona được chèn vào chuỗi trước khi phân tích template, khiến ngoặc nhọn trong persona trở thành biến prompt. Hiện dùng partial binding; persona không tồn tại hoặc custom rỗng/quá dài bị từ chối.
- Lỗi agent trước đây được trả dưới dạng suggestion và đưa vào lịch sử. Hiện server trả error và không ghi lượt lỗi vào lịch sử.
- STT trước đây biến lỗi thực thi thành chuỗi rỗng, nhầm với không có giọng nói. Hiện lỗi được truyền lên; cấu hình cũng cho phép xóa initial prompt.
- Lỗi vector store trước đây bị biến thành không tìm thấy tài liệu. Hiện ngăn tạo câu trả lời khi truy xuất lỗi.
- Prompt bổ sung yêu cầu dùng ngôn ngữ câu hỏi, trả lời các phần câu hỏi, chỉ rõ thiếu bằng chứng, phân biệt lời khuyên chung với dữ kiện dự án và xem tài liệu/lịch sử là dữ liệu không đáng tin cậy. Đây là hướng dẫn hành vi, không phải hàng rào bảo đảm đúng sự thật.
- Giới hạn kích thước từng lượt hội thoại, mã hóa nội dung khi ghép lịch sử, xóa facts khi reset và thêm khóa cho registry phiên.

## Những giới hạn còn lại

| Ưu tiên | Giới hạn | Ảnh hưởng / hướng xử lý |
| --- | --- | --- |
| P1 | RAG lấy top-k dù độ liên quan thấp; chưa có ngưỡng hoặc reranker | Tài liệu không liên quan vẫn có thể được dùng. Cần bộ câu hỏi có nhãn để hiệu chỉnh ngưỡng, không chọn một giá trị tùy ý. |
| P1 | Chưa đối chiếu từng nhận định với đoạn nguồn | Có nguồn liên quan không chứng minh câu trả lời đúng. Cần cấu trúc claim → evidence và đánh giá hỗ trợ/không hỗ trợ. |
| P1 | Tệp đã xóa không tự bị loại khỏi chỉ mục; tệp rỗng có thể giữ nội dung cũ | Cần manifest theo phạm vi ingest và cơ chế xóa an toàn sau khi quét thành công. |
| P1 | Ingest, clear và query có thể chồng nhau | Có thể đọc trạng thái chỉ mục đang cập nhật. Cần khóa hoặc phiên bản chỉ mục nhất quán. |
| P1 | Prompt injection chỉ được giảm thiểu bằng prompt và giới hạn công cụ | Chưa có kiểm thử đối kháng với mô hình thật; không thể kết luận đã loại bỏ prompt injection. |
| P2 | Web search trả chuỗi tóm tắt, thiếu provenance có cấu trúc | Không dùng web snippets làm bằng chứng chính xác cho số liệu hoặc hành vi dự án; cần URL, ngày và trích đoạn. |
| P2 | Ba vòng ReAct có thể không đủ cho câu hỏi nhiều phần | Hết vòng lặp hiện trở thành lỗi rõ ràng, nhưng chưa có chiến lược phân rã hay retry có giới hạn. |
| P2 | Lịch sử giới hạn theo số message/ký tự, chưa theo token | Có thể vượt ngân sách ngữ cảnh hoặc mất thông tin quan trọng; cần ngân sách token và tóm tắt có nguồn. |
| P2 | Facts chưa được đưa vào prompt; lịch sử chỉ lưu key point | Chưa có bộ nhớ facts hoạt động hoàn chỉnh; dễ mất chi tiết câu trả lời cũ. |
| P2 | Bộ tải chủ yếu PDF có text và các phần mở rộng mã/text đã liệt kê | Chưa có OCR, DOCX, PPTX, bảng tính hoặc đầy đủ phần mở rộng như TSX/JSX. |
| P2 | STT chưa lọc theo độ tin cậy của từng segment | Chưa đo WER tiếng Việt/Anh, nhiễu, tên riêng hay hiện tượng tạo chữ từ âm thanh yếu. |
| P2 | Cấu hình ngôn ngữ/prompt STT dùng chung và thay đổi khi đang xử lý | Cần snapshot cấu hình cho mỗi request và kiểm tra mã ngôn ngữ hợp lệ. |

## Kiểm thử đã chạy

13 kiểm thử đạt: gồm 10 kiểm thử parser/context/orchestration AI và 3 kiểm thử truy cập. Orchestration dùng provider giả để kiểm tra thứ tự truy xuất, nguồn và hành vi khi lỗi; không gọi Ollama, Chroma hoặc Whisper. Python compileall và git diff --check đạt.

Chưa thể suy ra tỷ lệ trả lời đúng hoặc mức bao quát kiến thức từ các kiểm thử này. Đánh giá tiếp theo cần câu hỏi nhiều phần, câu hỏi ngoài tài liệu, tài liệu mâu thuẫn/cũ, câu hỏi nối tiếp, số liệu cần tính, nội dung gây nhiễu prompt và bản ghi âm có đáp án chuẩn.
