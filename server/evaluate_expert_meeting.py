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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-url", required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--style", choices=["plain", "technical"], default="technical")
    args = parser.parse_args()
    from config import settings
    settings.ollama_model = args.model
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

        def evaluate(case):
            role, question = case
            ctx = SessionContext("expert-" + role)
            ctx.set_fact("presentation_topic", "FPTEELiterature: học liệu và thi thử cho học sinh, giáo viên, trường học")
            started = time.perf_counter()
            try:
                result = agent.run(question, ctx)
                return {"role": role, "question": question, "seconds": round(time.perf_counter()-started, 2), "answer": result}
            except Exception as exc:
                return {"role": role, "seconds": round(time.perf_counter()-started, 2), "error": type(exc).__name__}

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            answers = list(pool.map(evaluate, CASES))
        report = {"scope": "Generated Vietnamese expert questions; real RAG/model; concurrent independent agent sessions, not network or acoustic meeting test; semantic review required", "model": args.model, "style": args.style,
                  "workers": args.workers, "evidence_sha256": hashlib.sha256(args.evidence.read_bytes()).hexdigest(),
                  "elapsed_seconds": round(time.perf_counter()-started, 2), "answers": answers}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "answers"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
