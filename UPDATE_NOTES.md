# Cập nhật: bảo mật, độ ổn định và kiểm tra logic AI

## Audit đối kháng + giọng nói — 2026-10-17

- Thêm `scripts/voice_audit.py`: 16 ca gồm 6 nhóm phản biện + prompt injection + đòi bịa số liệu + câu mơ hồ + lệch chủ đề + tiếng Anh; chạy cả chế độ text và chế độ giọng nói tổng hợp espeak (đo WER so với câu gốc). Ghi `results.json`/`summary.md`, có `--generate-audio`.
- Kết quả chạy thật (máy GPU, dự án ShieldCall VN, LLM cloud): phần lớn câu trả lời **có căn cứ và trung thực** — tự nói "tài liệu không nêu" cho chi phí/số người dùng/Truecaller/container escape; từ chối in system prompt; từ chối bịa p99; từ chối trả lời thời tiết. WER giọng espeak ~0.65–1.6 nên nhận dạng méo nặng (giới hạn của TTS robot, không phải lỗi đường truyền).
- **Bug thật tìm được nhờ audit**: `answer_review` từ chối nhầm hai loại câu trả lời ĐÚNG, khiến 4/16 ca trả về "Không thể tạo câu trả lời":
  1. Câu mơ hồ ("Cái đó chạy như thế nào?") — hỏi lại một câu ngắn là đúng, nhưng reviewer đòi phải giải thích → `missing_part`.
  2. Câu so sánh với sản phẩm ngoài tài liệu (Truecaller/Google Safe Browsing) — trả lời "tài liệu không nêu" là đúng, nhưng reviewer đòi so sánh bằng kiến thức chung → `missing_part`.
  3. Phần còn lại là **không tất định**: cùng câu hỏi lúc lỗi lúc qua (reviewer là LLM cloud).
- Đã sửa: thêm 2 quy tắc vào `REVIEW_PROMPT` (chấp nhận hỏi lại khi câu mơ hồ; chấp nhận "tài liệu không nêu" khi câu hỏi đòi so sánh với thứ ngoài bằng chứng), và đổi sửa lỗi thành vòng lặp có giới hạn `AGENT_MAX_REPAIRS` (mặc định 2) thay vì sửa 1 lần rồi bỏ. Vẫn từ chối nếu còn lỗi sau khi sửa (không hiển thị câu chưa đạt).
- Đã cập nhật test `test_agent_contract` cho hành vi mới (126 test host, 3 lỗi import do thiếu phụ thuộc).
- **Mở rộng audit lên 34 ca** (thêm 18 ca thực tế/hiểm: giám khảo gay gắt, tiền đề sai về tech stack, tin đồn bị hack, đòi bảo đảm 100%, câu ghép, câu cụt, áp lực cảm xúc đòi số bịa, hỏi tính năng không tồn tại, Nghị định 13, injection trong tài liệu trích dẫn, "developer mode", "Tại sao?"). **Kết quả cuối: 34/34 kỳ vọng đạt**, latency trung vị 5,6 s. Artifact: `validation/audit-2026-10-17/`.

## Tài liệu phản biện sâu hơn (schema v2) — 2026-10-17

- Bộ câu hỏi giờ mỗi câu có thêm: **bằng chứng cần chuẩn bị** (`proof_needed`), **lỗi dễ mắc** (`pitfall`), **câu hỏi truy tiếp dự kiến** (`follow_ups`) — ngoài mục đích/dàn ý/hỏi tiếp đã có.
- Kịch bản phản biện thêm **câu chốt** (`closing`) và **cách trả lời nếu bị truy tiếp** (`second_followup`).
- Dàn ý thêm **thời lượng** từng phần (`timing`).
- **Mục mới `rehearsal`**: kế hoạch luyện tập theo phút, **danh sách câu dễ mất điểm cần tránh**, và checklist chuẩn bị trước khi lên — xuất thành `05-rehearsal.md`.
- Panel dashboard (tab CHUẨN BỊ PHẢN BIỆN) hiển thị luôn bằng chứng cần chuẩn bị / lỗi dễ mắc / câu hỏi truy tiếp.
- Bump `_SCHEMA` lên `v2` để cache cũ tự tạo lại; thêm test cho `validate_rehearsal`, `closing`/`second_followup`, `timing` và render đủ 6 phần (150 test trong container OK).
- **Bug thứ 5 do audit tìm được**: câu hỏi cụt không có ngữ cảnh ("Tại sao?") bị model **gán bừa vào đoạn tài liệu đầu tiên** rồi trả lời sai trọng tâm (thay vì hỏi lại). Đã sửa tất định: `needs_clarification()` + `clarification_answer()` trong `agent_service` — câu hỏi trống ngữ cảnh dạng đại từ/bare-interrogative được trả lời bằng một câu hỏi lại ngắn (kèm test), không phụ thuộc model.
- **Bug thứ 6 do audit tìm được**: reviewer có lúc **tự mâu thuẫn** — gán `unsupported_claim` nhưng ngay trong chi tiết lại ghi "The evidence supports this: README.md says…". Đã thêm quy tắc vào `REVIEW_PROMPT` (không gán unsupported_claim khi bằng chứng có hỗ trợ) và một bộ lọc hẹp `drop_self_contradictory()` loại đúng những issue tự mâu thuẫn (kèm test). Vẫn giữ nguyên tắc an toàn: sau khi sửa mà còn lỗi thì **từ chối trả lời**, không hiển thị câu chưa đạt.
- Tăng `AGENT_MAX_REPAIRS` mặc định 2 → 3 để bù tính không tất định của reviewer. Giới hạn còn lại: khoảng 1/34 ca vẫn có thể bị reviewer từ chối thoáng qua (cùng câu lúc lỗi lúc qua); hệ thống **từ chối trả lời** thay vì đưa câu sai — bấm lại phím là được.
- Sau khi sửa, chấm lại bộ ca text: **16/16 kỳ vọng đạt** (bản chấm cũ tự báo sai 3 ca vì bắt chữ "system prompt" trong câu từ chối, thiếu mẫu từ chối tiếng Anh, và kỳ vọng sai ở ca tài liệu thật sự có số liệu). Artifact: `validation/audit-2026-10-17/`.
- **Bug hạ tầng tìm được khi chạy giọng nói**: một lần container báo `CUDA failed ... no CUDA-capable device` (NVML lỗi thoáng qua sau vài lần tạo lại container) → mọi câu đều "Internal pipeline error". Tạo lại container thì hết (transient), nhưng đã thêm **fallback CPU** trong `TranscriberService.ensure_loaded` để GPU trục trặc thì vẫn nhận dạng được (chậm hơn), kèm `whisper_device` trong `/health`. Thêm test `test_transcriber_fallback`.
- **Bug nhận dạng quan trọng tìm được khi chạy giọng nói**: với audio không rõ, Whisper **đọc lại chính câu prompt gợi ý từ vựng** làm transcript (ví dụ "Thuyết bảo vệ dự án, phần mềm, công nghệ, kiến trúc..."), rồi engine tưởng đó là câu hỏi — đúng kiểu "lấy sai câu". Đã thêm `_echoes_prompt()`: nếu transcript chỉ là prompt đọc lại (≥80% token nằm trong prompt) thì coi như "không có tiếng nói" và bỏ. Thêm test.

## Chạy thật trên máy GPU và LLM cloud — 2026-10-17

Đã build và chạy thật trên máy này (Ubuntu 26.04, NVIDIA RTX 4070 SUPER 12GB, driver 615.71):

- Docker GPU: cài NVIDIA Container Toolkit; `docker run --gpus all nvidia-smi` thấy GPU; image dự án cài `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`, container thấy `/dev/nvidia*` và `ctranslate2.get_cuda_device_count() == 1`.
- Whisper trên GPU: nạp model `cuda/float16` qua `/api/config/warmup` (tiny 13s, small 53s gồm tải). Cùng clip 3,7 giây: CPU tiny 14.763 ms so với GPU tiny 1.249 ms (~12 lần), GPU small 976 ms. Tổng một câu hỏi thật 6,5 giây (LLM cloud chiếm 5,5 giây).
- LLM cloud: `deepseek-v4.1-flash:cloud` chạy qua Ollama daemon của máy (không suy luận local). `/api/simulate` trả 200 với câu trả lời có căn cứ, trích `[document_service.py]`, `[response_style.py]`, `review_status: model_reviewed`.
- RAG trong Docker: `verify-path` `/host/server/services` 25 tệp, `ingest` 172 chunk, sinh bộ tài liệu markdown (qa/rebuttal/evidence) thành công và gọi lại thì `cached: true`.
- Bảo mật: thiếu API key trả 401; bash tool chặn `/etc/passwd` nhưng cho URL; `/host` chỉ đọc; `/etc` bị từ chối khi duyệt.
- Dịch vụ local: `host.docker.internal` → `172.17.0.1`; dịch vụ bind `0.0.0.0` vào được (HTTP 200), còn Ollama bind `127.0.0.1` thì bị từ chối. Đã thêm unit systemd `ollama-docker-bridge` dùng socat bind `172.17.0.1:11435` → `127.0.0.1:11434` để container nối Ollama mà không mở ra LAN.
- Tailscale: đặt `BIND_ADDRESS=100.115.199.119` (IP Tailscale của máy) để publish panel/WebSocket lên tailnet; kiểm tra `http://100.115.199.119:8765/health` trả 200, thiếu key 401, đúng key 200. README ghi rõ giữ `API_TOKEN` và không mở ra Internet.
- Chuẩn bị cho dự án `/data/Sentinel_Team_Project`: `HOST_DOCS_ROOT=/data/Sentinel_Team_Project` (mount chỉ đọc tại `/host`); panel duyệt thấy `backend/`, `frontend/`, `docs/`, `_minhchung/`; `verify-path` báo 526 tệp chỉ mục được (bỏ qua `.venv*`, `node_modules`, `dist`, `build`).
- Lỗi phát hiện khi chạy thật: service `ollama` publish cổng 11434 đụng Ollama sẵn có trên máy → bỏ publish (container vào qua network `ollama:11434`); thêm volume cache HuggingFace `./data/hf-cache` để không tải lại model mỗi lần tạo container; Whisper nạp model lần đầu chỉ tải một lần.
- Lỗi phát hiện khi chạy full test **trong container** (137→138 test, OK): khi đã đặt `API_TOKEN`, `TokenStore` vẫn sinh thêm `data/.api-token`, và tệp đó lọt vào nhánh xác thực dự phòng khiến các test giả lập `api_token=""` bị 401. Đã sửa: khi có token từ môi trường thì không sinh tệp; `rotate()` cũng không ghi tệp khi đã có token môi trường (tránh tệp thừa mâu thuẫn). Test rotate nay dùng đường dẫn tạm. Chạy full suite trong image cuối **2 lần liên tiếp: 139 test OK** (1 skip do có ffmpeg), không còn rác.
- Lỗi phát hiện khi tạo bộ tài liệu cho ShieldCall VN: `num_predict=4096` quá nhỏ nên JSON của pack bị cắt (`done_reason=length`) → mất `rebuttal`/`outline`/`cheatsheet` (trạng thái `partial`). Đã sửa: thêm `LLM_MAX_OUTPUT_TOKENS` và `DOCUMENT_MAX_OUTPUT_TOKENS` (16384), nâng giới hạn `parse_json_object` cho pack lên 200k ký tự, và **gọi lại từng phần còn thiếu** thay vì bỏ. Tạo lại bộ ShieldCall VN: `status: success`, đủ 5 loại tài liệu.

## Luồng audio liên tục, Opus và cấu hình client — 2026-10-17

- Client Windows: thêm ô **API Key** và **Presentation Topic** trong Settings (lưu cùng appsettings), tự gửi `set_topic` khi kết nối lại để neo ngữ cảnh. `StreamContinuously` (mặc định bật) gửi PCM liên tục về server, có ngưỡng backlog để không phình bộ nhớ; khi tắt thì giữ hành vi cũ (gửi N giây rồi mới trigger).
- Hotkey giờ gửi `{"type":"trigger","request_id":...,"seconds":N}`: server phân tích đúng N giây gần nhất và xoá buffer sau đó, nên câu hỏi cũ không lẫn vào câu trả lời mới.
- Server WebSocket: đổi sang cửa sổ trượt — khi vượt `MAX_AUDIO_SECONDS` thì bỏ audio cũ nhất thay vì xoá sạch rồi báo lỗi; logic tách ra `services/audio_buffer.py` và có kiểm thử riêng.
- Định dạng tệp tạm cho Whisper: mặc định **M4A (Opus)** qua ffmpeg (`TRANSCRIPTION_AUDIO_FORMAT=m4a|ogg|wav`, đổi được trong tab Engine Metrics). Nếu ffmpeg/Opus lỗi thì tự thử lại bằng WAV nên không bao giờ chặn nhận dạng.
- Whisper nạp **lazy** thay vì lúc khởi động (trước đây tải model ngay, Docker có thể chết nếu mạng lỗi); thêm `POST /api/config/warmup` và hiển thị trạng thái model trong panel để nạp trước.
- Giữ PCM thô trên WebSocket thay vì nén Opus khi truyền: server thường chạy nội bộ/LAN nên 32 KB/s không phải nút cổ chai, còn nén thêm sẽ tăng độ trễ và thêm phụ thuộc codec; đây là lựa chọn tối ưu cho độ trễ. Nếu triển khai qua Internet, có thể bật Opus trên đường truyền sau.

## Máy chủ Docker, bảng quản trị từ xa và tài liệu markdown — 2026-10-17

- Docker server có ba điểm gắn: thư mục máy chủ chỉ đọc tại `/host` (`HOST_DOCS_ROOT`), dữ liệu ghi được tại `/app/data`, và thư mục xuất markdown riêng (`EXPORT_HOST_DIR`). Entrypoint tự sinh `API_TOKEN` khi chưa có và ghi vào `data/.api-token`; giá trị trong `.env` luôn được ưu tiên. Thêm `scripts/bootstrap_env.py` để tạo khoá ngoài Docker, và `docker-entrypoint.sh`, `.dockerignore`, `HEALTHCHECK`.
- Hỗ trợ GPU: image cài sẵn CUDA runtime/cuBLAS/cuDNN (`requirements-gpu.txt`, build arg `INSTALL_CUDA`), cả hai service yêu cầu `gpus: all`, Whisper mặc định `cuda`/`float16`/`small`. Cần NVIDIA Container Toolkit trên máy chủ. Máy CPU đặt `INSTALL_CUDA=false`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8` và bỏ `gpus:`.
- Nối dịch vụ local: thêm `host.docker.internal:host-gateway` và biến `OLLAMA_URL` để trỏ tới Ollama chạy trực tiếp trên máy (`http://host.docker.internal:11434`) mà không đụng `OLLAMA_BASE_URL` dùng cho chạy local.
- Bảng quản trị từ xa (dashboard) thêm: duyệt thư mục trên máy chủ (`/api/fs/roots`, `/api/fs/list`) giới hạn trong các root cấu hình; xoay khoá API (`/api/admin/token/rotate`); bật/tắt công cụ agent; đặt mặc định panel và đề tài tạo trước; dọn rác và xem dung lượng (`/api/maintenance/*`).
- Tính năng AI tạo tệp markdown: bộ câu hỏi, kịch bản phản biện, dàn ý trình bày, phiếu nhắc nhanh và phụ lục bằng chứng, kèm `defense-pack.md` và `manifest.json`. Cache theo hash nội dung và dấu vân tay chỉ mục nên lần sau không gọi model; `/api/documents/prebuild` tạo trước theo danh sách đề tài. Mọi tệp ghi rõ là tài liệu AI chuẩn bị, giữ mã bằng chứng và không coi là số liệu đã đo.
- Thêm lại công cụ cho agent theo hướng chuẩn vòng lặp tool call: `ingest_documents` và `bash` (mặc định TẮT). Bash bị giới hạn bằng thời gian chờ, giới hạn đầu ra, danh sách lệnh cấm và chỉ cho phép đường dẫn tuyệt đối nằm trong root. Đây KHÔNG phải sandbox: khi bật, model chạy được mọi thứ tiến trình server làm được — chỉ bật khi mọi người gọi server đều đáng tin.
- Dọn rác: `CLEANUP_ON_STARTUP` xoá tệp audio tạm (giữ nguyên marker khôi phục chỉ mục), panel dọn tệp cũ và log theo số ngày lưu; `scripts/cleanup.sh` và `scripts/cleanup.ps1` dọn cache Python/.NET, media lẫn và tùy chọn prune Docker.
- Thêm kiểm thử cho token store, duyệt đường dẫn, cài đặt panel, dọn rác, công cụ bash, kiểm tra tài liệu và dịch vụ tài liệu. Chưa chạy với Ollama/Whisper/Chroma thật trong môi trường này; các kiểm thử đó sẽ chạy khi đủ phụ thuộc.

## Goal professional và vòng nghiệm thu — 2026-10-17

- Goal đang hoạt động, chưa đánh dấu nghiệm thu.
- Thêm rà soát có giới hạn một lần sửa, chặn câu vẫn lỗi và không lưu lịch sử; sửa client JSON Ollama để nhận final content, timeout và giới hạn đầu ra.
- Sửa vòng đời RAG cho tệp xóa/rỗng, khóa đọc–ghi và marker sự cố qua khởi động lại. Tách ID kết nối, lưu các ý để hỏi tiếp và trả đúng evidence ở simulation.
- 77 kiểm thử backend qua. Đo 12 audio người thật có lời chuẩn: WER base 46,86%, small 25,74%, medium 11,55%; medium thêm nhiễu 15 dB 14,52%. Mẫu chỉ có 5 câu khác nhau.
- Chạy 8 phiên agent: tập phát triển 16/16 được engine cho qua, bộ giữ riêng 21/24. Đọc tay vẫn có lỗi gán hành vi sai API và thiếu ý kiểm thử; không gọi đây là độ chính xác.
- Phát lại podcast tiếng Việt với medium hết 38,657 giây. Chưa nghiệm thu hội trường/nói chồng hoặc audio đồng thời qua mạng. Chỉ đẩy số liệu đã lược dữ liệu riêng.

## Chuẩn bị phản biện và bài phỏng vấn ghi âm thật — 2026-10-16

Thêm tab dashboard và API `/api/defense/prepare` cho bộ câu hỏi theo sáu nhóm, nguồn tham khảo và checklist chuẩn bị; phân biệt rõ câu AI tạo với câu hỏi lịch sử. WebSocket có `set_topic`, simulation nhận đề tài để neo ngữ cảnh. Thêm runner replay giọng người thật, manifest nguồn/hash/timestamp, metric WER chỉ khi có reference và bộ test schema/API/UI. Bài chạy dùng sản phẩm FPTEELiterature trên server cùng ba đoạn hỏi từ podcast chính thức Android Developers.

## Trả lời dễ hiểu cho người lớn — 2026-10-16

Mặc định `RESPONSE_STYLE=plain`: nói ngắn, từ quen thuộc, giữ số liệu và mức chắc chắn; có `technical` để chọn cách nói chuyên môn. Thêm bước biên soạn cuối dựa trên evidence, kiểm tra ví dụ với tối đa một lần sửa và bộ lọc hẹp cho chỉ dẫn ghi đè prompt trong tài liệu. Đã chạy so sánh 10 câu trước/sau, nhóm câu mới và regression, cùng 30 kiểm thử logic trên server. Các giới hạn còn lại và chi phí thời gian đã được ghi trong mục giới hạn bên dưới.

## Kiểm thử server bổ sung — 2026-10-16

Đã chạy trên môi trường riêng: 16 kiểm thử đạt, embedding Ollama + Chroma thật, agent cloud với ba case giả lập, Whisper tiny trên CPU và toàn luồng WebSocket bằng FastAPI TestClient. Sửa parser ReAct để nhận JSON hợp lệ trực tiếp và bổ sung cấu hình `OLLAMA_EMBEDDING_BASE_URL`. Thêm `server/tools/runtime_smoke.py`, `server/tools/protocol_smoke.py` và kết quả gốc. Các mục giới hạn bên dưới mô tả mốc cập nhật ban đầu.

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

Xem DEVELOPMENT.md cho các mốc tiếp theo; server/tools/benchmark.py để đo trên máy có đủ môi trường AI.
# 2026-10-16 — thử chuyên gia tiếng Việt và nhiều phiên

- Thêm bộ đánh giá 8 vai trò trên bằng chứng FPTEELiterature thật, 4 phiên agent đồng thời.
- Sửa technical để soạn JSON có căn cứ, phục hồi khi planner lỗi; 47 kiểm thử qua.
- Thêm tùy chọn tiếng Việt / Whisper / phong cách cho phát lại bản ghi người thật.
- Đã chạy audio Vietsuccess tiếng Việt; không dùng từ khóa để tuyên bố độ chính xác.
- Cấu trúc hợp lệ tăng 4/8 → 8/8, nhưng còn lỗi nội dung nghiêm trọng; **chưa sẵn sàng họp chuyên gia**.

