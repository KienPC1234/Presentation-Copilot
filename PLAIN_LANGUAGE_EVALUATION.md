# Đánh giá câu trả lời dễ hiểu cho người lớn — 2026-10-16

## Mục tiêu

Theo xác nhận của người dùng, đối tượng vẫn là người lớn. “Dễ hiểu như nói với trẻ 4 tuổi” được hiểu là dùng từ quen thuộc, trả lời thẳng, giải thích ngắn và có ví dụ khi cần; không dùng giọng nói với trẻ em và không đơn giản hóa sai sự thật.

Mặc định mới: `RESPONSE_STYLE=plain`. Chọn `RESPONSE_STYLE=technical` trong server/.env và khởi động lại để giữ cách nói chuyên môn. Persona vẫn định hướng quá trình tìm thông tin; chế độ plain có bước biên soạn câu trả lời cuối từ evidence và kết quả công cụ, không lấy câu trả lời nháp của model làm bằng chứng. LLMService dự phòng dùng chung hướng dẫn phong cách và bộ lọc; chưa có đánh giá model thật riêng cho đường dự phòng này.

## Phương pháp và dữ liệu

- Chạy trên môi trường riêng của server, model `gpt-oss:120b-cloud`.
- So sánh trước/sau trên cùng 10 câu hỏi với tài liệu giả lập: thẻ truy cập 17 phút, dữ liệu chờ 9 ngày, thiếu thông tin hiệu năng/cách làm mới thẻ/offline. Baseline là engine tại commit d43870b, trước thay đổi phong cách.
- Retriever cố định theo từng case để tách chất lượng trả lời khỏi chất lượng tìm kiếm. Đây không phải đánh giá recall của RAG, STT hoặc tình huống tài liệu thực tế.
- Sau vòng phát triển có thêm 4 câu ban đầu chưa dùng để chỉnh prompt: tính giờ hết hạn, có tự động xóa hay không, xin ví dụ, tài liệu mâu thuẫn. Khi dùng kết quả xin ví dụ để sửa tiếp, case đó trở thành regression test; không còn được coi là kiểm tra độc lập.
- Có kiểm tra bổ sung câu hỏi tiếng Anh với tài liệu tiếng Việt. Trước sửa từng có trả lời sai ngôn ngữ; regression cuối trả lời bằng tiếng Anh.
- Đã giữ cả JSON trước, các vòng trung gian bị lỗi và kết quả sau trong `validation/plain-language-2026-10-16/`. Các regex chỉ là kiểm tra từ/cụm từ, không phải máy chấm đúng sự thật. Ví dụ regex `như` trước đây nhầm `nhưng`; đã sửa ranh giới từ và không sửa lại dữ liệu lịch sử để che lỗi.

## Kết quả quan sát

| Tiêu chí | Trước | Sau, vòng 10 câu cuối |
| --- | --- | --- |
| Lỗi không sinh được câu trả lời | 2/10 | 0/10 |
| Độ dài trung bình trên 8 case có câu trả lời ở cả hai phía | 91,4 đơn vị tách bằng khoảng trắng | 19,8 đơn vị |
| Lượt khớp danh sách hẹp jargon (TTL, p99, QPS, endpoint, …) | 18 | 0 |
| Trung vị thời gian xử lý 10 case | 2,39 giây | 3,70 giây |

Độ dài được tính trên key_point, keywords và framework_steps; không phải số từ ngôn ngữ học của tiếng Việt. Không dùng số khớp jargon để khẳng định mọi câu đều thuần Việt: một số từ như token/offline vẫn xuất hiện. Thời gian là quan sát một lượt, chưa phải benchmark có kiểm soát; plain thường thêm một lần gọi model, và có thể thêm một lần sửa nếu thiếu ví dụ.

Đọc thủ công vòng cuối:

| Tình huống | Nhận xét |
| --- | --- |
| Hai dữ kiện trong cùng câu | Giữ đúng 17 phút và 9 ngày, không thêm quy trình làm mới |
| Hỏi tốc độ chưa có trong tài liệu | Nói tài liệu không cho biết; không bịa số |
| Hai tài liệu ghi 17/30 phút | Nêu cả hai, không tự chọn hoặc bịa lý do khác phiên bản |
| Đổi 17 phút ra giây | Đúng 1020 giây |
| Nhầm thời hạn thẻ với lưu dữ liệu | Sửa nhầm lẫn, giữ hai mốc riêng |
| Chỉ dẫn gây nhiễu trong tài liệu | Bộ lọc loại đoạn ghi đè rõ ràng; câu trả lời giữ 17 phút và không dẫn nguồn đoạn đã loại |
| Không có bằng chứng dùng offline | Nói chưa rõ, không đoán tính năng |
| Hỏi tại sao thẻ hết hạn | Nêu tài liệu không cho lý do, phân biệt lý do bảo mật thông thường |
| Câu hỏi tiếp nối về dữ liệu chờ | Dùng được ngữ cảnh và trả lời 9 ngày |
| “Cái đó có nhanh không?” | Không bịa hiệu năng, nhưng vẫn chưa luôn hỏi rõ đối tượng; hữu ích một phần |

Ở nhóm câu mới ban đầu, câu hỏi xin ví dụ chỉ được trả định nghĩa. Một vòng sửa prompt sau đó còn gán 9 ngày vào ví dụ email — không chấp nhận được và đã giữ trong `plain-example-regression.json`. Bổ sung kiểm tra thiếu ví dụ và một lần sửa có giới hạn. Regression cuối (`plain-example-repaired.json`) giải thích dữ liệu chờ bằng người xếp hàng; không gán thời gian giữ của dự án vào người trong ví dụ.

## Thay đổi triển khai

- Giữ số liệu, đơn vị, mâu thuẫn và điều chưa biết; bỏ yêu cầu phải điền đủ các bullet hoặc thuật ngữ.
- Thêm bước JSON plain có cấu trúc, dựa trên evidence và kết quả công cụ thay vì lặp lại câu trả lời nháp chưa kiểm chứng.
- Nếu bước lập kế hoạch agent lỗi, thử biên soạn plain một lần từ evidence đã truy xuất; lỗi truy xuất không được coi là thiếu tài liệu rồi bỏ qua.
- Chọn ngôn ngữ theo câu hỏi, tách khỏi ngôn ngữ của tài liệu.
- Kiểm tra yêu cầu ví dụ ở key_point/framework_steps; thiếu thì viết lại tối đa một lần, vẫn thiếu thì thêm metadata `quality_warnings: ["missing_requested_example"]`. Metadata này chưa có badge riêng trong WPF.
- Bộ lọc hẹp loại các đoạn chứa chỉ dẫn ghi đè prompt rõ ràng, áp dụng trước cấp evidence và khi nhận kết quả rag_search. Đây là heuristic: có thể bỏ nhầm tài liệu trích dẫn một cuộc tấn công, và không chặn được mọi dạng prompt injection.
- 30/30 kiểm thử unit/contract đạt trên server có LangChain thật. Kiểm thử này xác minh luồng, schema, phong cách cấu hình, giới hạn sửa và bộ lọc; không thay đánh giá nội dung.
- Kiểm thử tích hợp sau thay đổi: Chroma + embedding thật và ba câu hỏi của `runtime_smoke.py` đạt. Luồng PCM → Whisper → agent → WebSocket qua TestClient đạt; lần cuối khoảng 4,89 giây. JSON nằm trong `plain-real-rag.json` và `plain-protocol.json`; đây vẫn chưa phải kiểm thử WPF qua mạng.

## Chạy lại

Tại thư mục server của môi trường kiểm thử:

```bash
../.runtime/bin/python evaluate_plain_language.py --model gpt-oss:120b-cloud \
  --style plain --label my-run --output ../plain-evaluation.json

../.runtime/bin/python evaluate_plain_language.py --model gpt-oss:120b-cloud \
  --style plain --suite holdout --label extra-cases --output ../extra-cases.json
```

`--style technical` trên bản mới không tái tạo baseline cũ d43870b, vì prompt và bộ lọc chung cũng đã thay đổi. Mỗi lần chạy dùng model thật và có thể có kết quả khác.

## Giới hạn trước khi kết luận chất lượng

Chưa có người dùng thực đánh giá mức hiểu, chưa đánh giá trẻ em, chưa có bộ tài liệu độc lập đủ lớn hay kiểm chứng tự động từng nhận định. Câu trả lời ngắn vẫn có thể sai. Ví dụ được nhận diện bằng dấu hiệu ngôn ngữ, không chứng minh ví dụ đúng; bộ lọc prompt cũng chỉ bao phủ một nhóm mẫu. Cần tiếp tục kiểm tra lời giải thiếu ý, thuật ngữ còn sót, số liệu không có nguồn và độ ổn định nhiều lần chạy. Không diễn giải kết quả này thành “độ chính xác 100%”.
