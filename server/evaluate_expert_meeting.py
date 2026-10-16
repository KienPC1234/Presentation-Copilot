"""Opt-in Vietnamese expert evaluation on real, locally supplied project evidence.

Generated questions, real model/RAG, independent concurrent sessions. This does
not simulate room acoustics, diarization or human understanding.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import math
from threading import local

CASES = [
    ("cto", "Nếu 500 học sinh nộp bài cùng lúc, có thể cam kết chịu tải không? Phân biệt bằng chứng hiện có, giả thuyết và phép đo cần làm trước khi cam kết."),
    ("teacher", "Học sinh chuyển tab hai lần có đủ kết luận gian lận và trừ điểm tự động không? Nêu giới hạn tín hiệu, cách giáo viên xem xét và quyền giải trình."),
    ("security", "Mã vào bài thi có đồng nghĩa phân quyền an toàn không? Cần kiểm tra quyền sở hữu bài làm, sửa ID và gửi lại yêu cầu như thế nào? Đừng khẳng định đã kiểm thử."),
    ("operations", "Mất mạng sát hạn nộp bài rồi gửi lại hai lần: hiện có gì trong mã nguồn, điều gì chưa chứng minh và cần kiểm thử thứ tự thời gian nào?"),
    ("finance", "Đầu tư mở rộng máy chủ hay sửa lỗi lưu bài trước? Nêu tiêu chí ảnh hưởng, rủi ro, chi phí và bằng chứng cần thu thập; không bịa số tiền hoặc tỷ lệ lỗi."),
    ("product", "Có tài liệu học và thi thử thì đã chứng minh cải thiện kết quả học chưa? Thiết kế phép đánh giá có nhóm so sánh, chỉ số và yếu tố gây nhiễu."),
    ("chair", "Trước cuộc họp quyết định triển khai toàn trường, tách ba mục: điều đã biết từ mã nguồn, điều chưa được đo và điều kiện dừng triển khai. Ai cần xác nhận từng mục?"),
    ("challenger", "Tôi khẳng định hệ thống dùng Firebase và tự trừ điểm khi rời tab. Hãy kiểm tra cả hai khẳng định theo tài liệu, không chiều theo tôi."),
]

HOLDOUT_CASES = [
    ("unknown_technology", "Chưa thấy Kafka trong trích đoạn thì có thể xác nhận sản phẩm không dùng Kafka không? Nêu giới hạn kết luận và tài liệu cần kiểm tra thêm."),
    ("cross_account", "Một học sinh biết mã phòng hợp lệ và khóa nộp của bạn khác. Thiết kế phép thử kiểm tra xem hoặc sửa bài người khác: nêu tài khoản thử, kết quả mong đợi và bằng chứng, không bịa đường dẫn API."),
    ("availability", "Có thể ký cam kết sẵn sàng 99,99% và không bao giờ mất bài dựa vào đoạn mã này chưa? Phân biệt điều đã biết, điều chưa đo và điều kiện trước khi ký."),
    ("retry_race", "Hai yêu cầu cùng khóa nộp đến đúng một thời điểm: có nhánh replay đã đủ chứng minh chỉ ghi một lần chưa? Cần phép thử đồng thời và kiểm tra dữ liệu nào?"),
    ("learning_bias", "Nhóm dùng thi thử có điểm cao hơn nhóm không dùng. Chưa phân nhóm ngẫu nhiên, trình độ đầu vào khác nhau: có thể kết luận sản phẩm tạo ra chênh lệch không? Thiết kế cách kiểm chứng."),
    ("priority_tradeoff", "Một lỗi lệch màu nút và một tính năng mới giúp học sinh khiếm thị làm bài: có phải cứ là lỗi thì luôn phải sửa trước tính năng? Nêu tiêu chí và dữ liệu cần có, không coi đây là lỗi đã có trong dự án."),
    ("rollout_recovery", "Hội đồng cần kế hoạch triển khai từng phần rồi quay lại bản cũ nếu sai điểm. Đề xuất điều kiện dừng, bảo toàn bài làm và người xác nhận; tách rõ những gì tài liệu chưa chứng minh."),
    ("two_claims", "Nhà tài trợ nói đã có AI cá nhân hóa và cơ chế phúc khảo tự động. Đối chiếu từng khẳng định với bằng chứng hiện có và nêu tài liệu hoặc phép thử cần bổ sung."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--review-model", default="")
    parser.add_argument("--answer-model", default="")
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--style", choices=["plain", "technical"], default="technical")
    parser.add_argument("--suite", choices=["development", "holdout"], default="development")
    parser.add_argument("--runs", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--case", help="Run one role ID for focused diagnosis")
    parser.add_argument("--trace-review", action="store_true", help="Save reviewer JSON feedback in the PRIVATE report")
    args = parser.parse_args()
    cases = HOLDOUT_CASES if args.suite == "holdout" else CASES
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
        if not cases:
            parser.error("No matching role ID in the selected suite")
    from config import settings
    settings.ollama_model = args.model
    settings.ollama_review_model = args.review_model
    settings.ollama_answer_model = args.answer_model
    settings.ollama_embedding_base_url = args.embedding_url
    settings.response_style = args.style
    from services.agent_service import AgentService
    from services.context_manager import SessionContext
    from services.rag_service import RAGService
    import tempfile
    with tempfile.TemporaryDirectory(prefix="copilot-expert-") as root:
        settings.chroma_persist_dir = root
        rag = RAGService()
        rag.ingest_documents(str(args.evidence))
        agent = AgentService(rag)
        state = local()
        if args.trace_review:
            reviewer = agent._review_llm

            class RecordingReviewer:
                def invoke(self, messages):
                    response = reviewer.invoke(messages)
                    payload = json.loads(messages[-1].content)
                    state.reviews.append({"feedback": response.content, "candidate": payload["candidate"]})
                    return response

            agent._review_llm = RecordingReviewer()

        def evaluate(task):
            run, (role, question) = task
            ctx = SessionContext(f"expert-{run}-{role}")
            ctx.set_fact("presentation_topic", "FPTEELiterature: học liệu và thi thử cho học sinh, giáo viên, trường học")
            started = time.perf_counter()
            state.reviews = []
            try:
                result = agent.run(question, ctx)
                answer = {"run": run, "role": role, "question": question, "seconds": round(time.perf_counter()-started, 2), "answer": result}
                if args.trace_review:
                    answer["review_trace"] = list(state.reviews)
                return answer
            except Exception as exc:
                return {"run": run, "role": role, "seconds": round(time.perf_counter()-started, 2), "error": type(exc).__name__}

        started = time.perf_counter()
        answers = []
        # Each run finishes before the next starts; workers bound active calls.
        for run in range(1, args.runs + 1):
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                answers.extend(pool.map(evaluate, [(run, case) for case in cases]))
        report = {"scope": "Generated Vietnamese expert questions; real RAG/model; concurrent independent agent sessions, not network or acoustic meeting test; semantic review required", "model": args.model, "answer_model": args.answer_model or args.model, "review_model": args.review_model or args.answer_model or args.model, "style": args.style,
                  "workers": args.workers, "evidence_sha256": hashlib.sha256(args.evidence.read_bytes()).hexdigest(),
                  "suite": args.suite, "runs": args.runs,
                  "elapsed_seconds": round(time.perf_counter()-started, 2), "answers": answers}
        blocked = sum(bool(a.get("error") or a.get("answer", {}).get("error")) for a in answers)
        latencies = sorted(a["seconds"] for a in answers)
        report.update({"valid_answers": len(answers) - blocked, "blocked_or_failed_answers": blocked,
                       "execution_gate_passed": blocked == 0,
                       "all_requests_p95_seconds": latencies[math.ceil(.95 * len(latencies)) - 1],
                       "percentile_method": "nearest rank; includes blocked requests; not semantic accuracy"})
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "answers"}, ensure_ascii=False))
        if blocked:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
