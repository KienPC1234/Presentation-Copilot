# Rà soát logic AI engine

**Trạng thái 2026-10-17:** goal professional đang hoạt động, chưa nghiệm thu. Đã có lớp rà soát/sửa có giới hạn, kiểm thử vòng đời RAG và phép đo ASR tiếng Việt. Xem `PROFESSIONAL_ACCEPTANCE.md` và `PROFESSIONAL_VALIDATION.md` cho kết quả hiện tại; các số kiểm thử trong phần ban đầu bên dưới là số liệu lịch sử.

**Bổ sung 2026-10-16:** đã chạy một số kiểm thử bằng mô hình thật trên server và sửa thêm lỗi parser ReAct. Xem `SERVER_VALIDATION.md` cùng JSON trong `validation/server-2026-10-16/`. Phần dưới là kết quả rà soát tĩnh ban đầu; chưa thể suy ra tỷ lệ chính xác tổng thể từ các smoke test mới.

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
| Đã sửa theo phạm vi | Nạp lại thư mục loại nguồn xóa/rỗng sau khi quét thành công | Có kiểm thử giữ nguyên phạm vi khác và hủy cập nhật khi đọc lỗi; chưa có watcher tự đồng bộ. |
| Đã sửa trong một instance | Ingest, clear và query dùng RLock; marker chặn đọc sau cập nhật dở dang | Có kiểm thử đọc–ghi và khởi động lại. Chưa hỗ trợ nhiều process cùng thư mục chỉ mục. |
| P1 | Prompt injection chỉ được giảm thiểu bằng prompt và giới hạn công cụ | Chưa có kiểm thử đối kháng với mô hình thật; không thể kết luận đã loại bỏ prompt injection. |
| P2 | Web search trả chuỗi tóm tắt, thiếu provenance có cấu trúc | Không dùng web snippets làm bằng chứng chính xác cho số liệu hoặc hành vi dự án; cần URL, ngày và trích đoạn. |
| P2 | Ba vòng ReAct có thể không đủ cho câu hỏi nhiều phần | Đã có bước soạn từ bằng chứng khi planner lỗi và một lần sửa theo review; vẫn thiếu phân rã yêu cầu con có kiểm chứng. |
| P2 | Lịch sử giới hạn theo số message/ký tự, chưa theo token | Có thể vượt ngân sách ngữ cảnh hoặc mất thông tin quan trọng; cần ngân sách token và tóm tắt có nguồn. |
| P2 | Facts hiện dùng presentation_topic, lịch sử lưu key point và các ý | Giới hạn prompt 24.000 ký tự; chưa có bộ nhớ facts có nguồn hay tóm tắt theo ngân sách token. |
| P2 | Bộ tải chủ yếu PDF có text và các phần mở rộng mã/text đã liệt kê | Chưa có OCR, DOCX, PPTX, bảng tính hoặc đầy đủ phần mở rộng như TSX/JSX. |
| P2 | STT chưa lọc theo độ tin cậy của từng segment | Chưa đo WER tiếng Việt/Anh, nhiễu, tên riêng hay hiện tượng tạo chữ từ âm thanh yếu. |
| P2 | Cấu hình ngôn ngữ/prompt STT vẫn dùng chung | Đã snapshot từng request, kiểm tra ngôn ngữ được model hỗ trợ và trả 422 khi sai; chưa có cấu hình riêng cho mỗi phiên. |

## Kiểm thử đã chạy

13 kiểm thử đạt: gồm 10 kiểm thử parser/context/orchestration AI và 3 kiểm thử truy cập. Orchestration dùng provider giả để kiểm tra thứ tự truy xuất, nguồn và hành vi khi lỗi; không gọi Ollama, Chroma hoặc Whisper. Python compileall và git diff --check đạt.

Chưa thể suy ra tỷ lệ trả lời đúng hoặc mức bao quát kiến thức từ các kiểm thử này. Đánh giá tiếp theo cần câu hỏi nhiều phần, câu hỏi ngoài tài liệu, tài liệu mâu thuẫn/cũ, câu hỏi nối tiếp, số liệu cần tính, nội dung gây nhiễu prompt và bản ghi âm có đáp án chuẩn.
